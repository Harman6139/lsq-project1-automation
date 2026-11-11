"""Evaluate fixed reporting policies on observed CZ portfolio histories.

All cutoffs are loaded from the completed chronological benchmark analysis.
The policy Monte Carlo error and joint-calendar bootstrap ranges describe
different conditional exercises and are reported separately.
"""

from hashlib import sha256
from itertools import combinations
from math import comb
from pathlib import Path
import json
import time

import numpy as np
import pandas as pd

from a9_data import ROOT, circular_indices, load_panel, read_design, read_french
from a9_metrics import combined_scores, raw_scores
from a9_reporting import moving_average_paths, prepare_ledger_inputs, transform_paths
from run_benchmarks import load_maps, point_decisions


WEIGHTINGS = ('original', 'value_weighted')
REPRESENTATIONS = ('spread', 'funded')
LAGS = (None, 1, 3, 6)
RATE_COLUMNS = ('baseline_rate', 'altered_rate', 'new_alert_rate', 'cleared_alert_rate',
                'changed_rate', 'conditional_baseline_rate', 'conditional_altered_rate',
                'conditional_new_alert_rate', 'conditional_cleared_alert_rate')


def file_hash(path):
    return sha256(path.read_bytes()).hexdigest()


def lag_name(lag):
    return 'permanent' if lag is None else str(lag)


def load_contexts(design):
    contexts = []
    dependencies = {}
    french = read_french()
    start = pd.Period(design['evaluation'][0], freq='M') - 6
    end = pd.Period(design['evaluation'][1], freq='M')
    for weighting in WEIGHTINGS:
        cutoff_path = ROOT / f'tables/cutoffs_{weighting}.csv'
        if not cutoff_path.is_file():
            raise RuntimeError(f'Locked cutoff table is required: {cutoff_path.name}')
        dependencies[str(cutoff_path.relative_to(ROOT))] = file_hash(cutoff_path)
        cutoff_table = pd.read_csv(cutoff_path, float_precision='round_trip')
        frame = load_panel(weighting).loc[start:end]
        cash = french.reindex(frame.index)['RF'].to_numpy()
        if len(frame) != 114 or not np.isfinite(frame.to_numpy()).all() or not np.isfinite(cash).all():
            raise ValueError('Expected 114 complete months including the actual six-month warm-up')
        maps = {}
        cutoffs = {}
        for months in design['window_lengths']:
            for representation in REPRESENTATIONS:
                map_path = ROOT / f'data/maps/{weighting}_{representation}_{months}.npz'
                dependencies[str(map_path.relative_to(ROOT))] = file_hash(map_path)
                maps[months, representation] = load_maps(map_path)
                rows = cutoff_table.loc[(cutoff_table['months'] == months)
                                        & (cutoff_table['representation'] == representation)
                                        & (cutoff_table['block'] == 12)]
                if rows.empty or rows['ordinary_cutoff'].nunique() != 1 or rows['selection_cutoff'].nunique() != 1:
                    raise ValueError('Cutoff table must identify one frozen cutoff pair per cell')
                cutoffs[months, representation] = {
                    'ordinary': float(rows.iloc[0]['ordinary_cutoff']),
                    'selection': float(rows.iloc[0]['selection_cutoff']),
                }
        contexts.append({'weighting': weighting, 'names': list(frame.columns),
                         'spread': frame.to_numpy().T, 'rf': cash,
                         'maps': maps, 'cutoffs': cutoffs})
    return contexts, dependencies


def evaluate(values, context, representation, months):
    scores = raw_scores(values)
    combined = combined_scores(scores['B'], scores['D'], context['maps'][months, representation])
    flags = point_decisions(scores, combined, context['cutoffs'][months, representation])
    return scores, flags


def basis_values(spread, rf, representation):
    return spread if representation == 'spread' else spread + rf[None, :]


def summaries(before_flags, after_flags, ledger):
    changed = ledger['has_observed_change']
    total = len(changed)
    changed_count = int(changed.sum())
    scheduled = ledger['scheduled_recognitions_after_window'].sum(axis=1)
    schedule_error = (float(np.max(np.abs(scheduled - ledger['closing_gap'])))
                      if ledger['lag'] is not None else np.nan)
    shared = {
        'n_strategies': total, 'changed_paths': changed_count, 'changed_rate': changed_count / total,
        'ledger_max_error': ledger['ledger_max_error'], 'gap_units': ledger['gap_units'],
        'maximum_opening_gap': float(np.max(ledger['opening_gap'])),
        'maximum_closing_gap': float(np.max(ledger['closing_gap'])),
        'mean_closing_gap': float(np.mean(ledger['closing_gap'])),
        'mean_scheduled_future_recognition': float(np.mean(scheduled)),
        'scheduled_settlement_error': schedule_error,
        'scheduled_settlement_verified': bool(ledger['lag'] is not None and schedule_error < 1e-11),
        'supplied_economic_tail_months': ledger['tail_months_provided'],
        'paths_with_outstanding_closing_gap': int(np.sum(ledger['closing_gap'] > 1e-12)),
        'actual_supplied_tail_fully_settled': ledger['fully_settled'],
    }
    for method, before in before_flags.items():
        after = after_flags[method]
        new = ~before & after
        cleared = before & ~after
        record = dict(shared, method=method,
                      baseline_alerts=int(before.sum()), altered_alerts=int(after.sum()),
                      new_alerts=int(new.sum()), cleared_alerts=int(cleared.sum()),
                      baseline_rate=float(before.mean()), altered_rate=float(after.mean()),
                      new_alert_rate=float(new.mean()), cleared_alert_rate=float(cleared.mean()))
        for label, values in [('baseline', before), ('altered', after), ('new_alert', new), ('cleared_alert', cleared)]:
            record[f'conditional_{label}_rate'] = float(values[changed].mean()) if changed_count else np.nan
        yield record


def candidate_selection_probabilities(baseline_sharpe, altered_sharpe, pool_size):
    """One designated candidate is included with K-1 unaltered candidates."""
    count = len(baseline_sharpe)
    indices = np.arange(count)
    worse = baseline_sharpe[None, :] < altered_sharpe[:, None]
    # Input strategy order is the predetermined tie-break used by the benchmark.
    worse |= ((baseline_sharpe[None, :] == altered_sharpe[:, None])
              & (indices[None, :] > indices[:, None]))
    np.fill_diagonal(worse, False)
    worse_counts = worse.sum(axis=1)
    denominator = comb(count - 1, pool_size - 1)
    return np.array([comb(int(available), pool_size - 1) / denominator
                     if available >= pool_size - 1 else 0.0 for available in worse_counts])


def selection_self_check():
    baseline = np.array([.1, .3, .3, -.1, .2])
    altered = np.array([.3, .3, .4, .1, .2])
    for pool_size in (1, 2, 4, 5):
        expected = []
        for candidate in range(len(baseline)):
            others = [i for i in range(len(baseline)) if i != candidate]
            outcomes = []
            for competitors in combinations(others, pool_size - 1):
                contestants = (candidate,) + competitors
                winner = min(contestants, key=lambda i: (-(altered[i] if i == candidate else baseline[i]), i))
                outcomes.append(winner == candidate)
            expected.append(np.mean(outcomes))
        np.testing.assert_allclose(candidate_selection_probabilities(baseline, altered, pool_size), expected, atol=1e-15)
        unchanged = candidate_selection_probabilities(baseline, baseline, pool_size)
        np.testing.assert_allclose(unchanged.mean(), 1 / pool_size, atol=1e-15)


def exact_selected_rows(context, representation, spread, rf, reported, ledger, before_flags, after_flags):
    baseline_sharpe = spread.mean(axis=1) / spread.std(axis=1, ddof=1)
    excess_reported = reported if representation == 'spread' else reported - rf[None, :]
    altered_sharpe = excess_reported.mean(axis=1) / excess_reported.std(axis=1, ddof=1)
    changed = ledger['has_observed_change']
    altered_sharpe[~changed] = baseline_sharpe[~changed]
    for pool_size in sorted(set(min(len(spread), size) for size in (20, 100, len(spread)))):
        probability = candidate_selection_probabilities(baseline_sharpe, altered_sharpe, pool_size)
        selected = float(probability.mean())
        changed_selected = float(np.mean(probability * changed))
        for method, flags in after_flags.items():
            joint = float(np.mean(probability * flags))
            changed_joint = float(np.mean(probability * changed * flags))
            yield {'weighting': context['weighting'], 'representation': representation,
                   'months': reported.shape[1], 'delta': .01, 'probability': 1.,
                   'lag': lag_name(ledger['lag']), 'K': pool_size, 'method': method,
                   'n_strategies': len(spread), 'changed_candidates': int(changed.sum()),
                   'designated_candidate_selection_probability': selected,
                   'joint_selected_alert_probability': joint,
                   'conditional_alert_given_selected': joint / selected if selected > 0 else np.nan,
                   'joint_selected_changed_probability': changed_selected,
                   'joint_selected_changed_alert_probability': changed_joint,
                   'conditional_alert_given_changed_selected': changed_joint / changed_selected if changed_selected > 0 else np.nan,
                   'joint_selected_new_alert_probability': float(np.mean(probability * ~before_flags[method] * flags)),
                   'population_fraction_designated': 1 / pool_size}


def point_analysis(contexts, common_picks, common_names):
    points, selected, smoothing = [], [], []
    name_index = {name: index for index, name in enumerate(common_names)}
    for context in contexts:
        strategy_indices = [name_index[name] for name in context['names']]
        for months in (108, 60):
            spread = context['spread'][:, -(months + 6):]
            rf = context['rf'][-(months + 6):]
            picks = common_picks[strategy_indices, -(months + 6):]
            for representation in REPRESENTATIONS:
                values = basis_values(spread, rf, representation)
                before_scores, before_flags = evaluate(values[:, 6:], context, representation, months)
                prepared = prepare_ledger_inputs(values, pick_draws=picks)
                for probability in (1., .5):
                    for delta in (.005, .01, .02):
                        for lag in LAGS:
                            ledger = transform_paths(prepared, delta, probability, lag, n_observed=months,
                                                     funded_nav=representation == 'funded')
                            reported = ledger['reported_returns']
                            after_scores, after_flags = evaluate(reported, context, representation, months)
                            shared = {'weighting': context['weighting'], 'representation': representation,
                                      'months': months, 'delta': delta, 'probability': probability,
                                      'target_policy': 'fixed_0.0005', 'lag': lag_name(lag)}
                            points.extend(dict(shared, **row) for row in summaries(before_flags, after_flags, ledger))
                            if months == 108 and probability == 1 and delta == .01:
                                selected.extend(exact_selected_rows(context, representation, spread[:, 6:], rf[6:],
                                                                    reported, ledger, before_flags, after_flags))
                for weight in (.25, .5, .75):
                    filtered = moving_average_paths(values, weight, n_observed=months)
                    after_scores, after_flags = evaluate(filtered['reported_returns'], context, representation, months)
                    for method, before in before_flags.items():
                        after = after_flags[method]
                        smoothing.append({'weighting': context['weighting'], 'representation': representation,
                                          'months': months, 'lambda': weight, 'method': method,
                                          'interpretation': 'symmetric causal payoff filter',
                                          'n_strategies': len(before), 'baseline_alerts': int(before.sum()),
                                          'filtered_alerts': int(after.sum()), 'baseline_rate': float(before.mean()),
                                          'filtered_rate': float(after.mean()),
                                          'new_alerts': int((~before & after).sum()),
                                          'cleared_alerts': int((before & ~after).sum()),
                                          'mean_acf_before': float(before_scores['acf1'].mean()),
                                          'mean_acf_after': float(after_scores['acf1'].mean()),
                                          'median_B_before': float(np.median(before_scores['B'])),
                                          'median_B_after': float(np.median(after_scores['B'])),
                                          'mean_D_before': float(before_scores['D'].mean()),
                                          'mean_D_after': float(after_scores['D'].mean()),
                                          'filter_identity_error': filtered['filter_identity_error']})
    return pd.DataFrame(points), pd.DataFrame(selected), pd.DataFrame(smoothing)


def policy_sensitivity(contexts, design, common_names):
    name_index = {name: index for index, name in enumerate(common_names)}
    rows = []
    draws = design['reporting']['probability_sensitivity_draws']
    for policy_index, policy in enumerate(('half_fixed_target', 'all_uniform_target')):
        for draw in range(draws):
            rng = np.random.default_rng(np.random.SeedSequence([design['seed'], 9, policy_index + 2, draw]))
            picks = rng.random((len(common_names), 114))
            target = (np.full((len(common_names), 114), .0005) if policy == 'half_fixed_target'
                      else rng.uniform(0., .001, (len(common_names), 114)))
            probability = .5 if policy == 'half_fixed_target' else 1.
            for context in contexts:
                strategy_indices = [name_index[name] for name in context['names']]
                for representation in REPRESENTATIONS:
                    values = basis_values(context['spread'], context['rf'], representation)
                    _, before_flags = evaluate(values[:, 6:], context, representation, 108)
                    prepared = prepare_ledger_inputs(values, target_draws=target[strategy_indices], pick_draws=picks[strategy_indices])
                    for delta in (.005, .01, .02):
                        for lag in LAGS:
                            ledger = transform_paths(prepared, delta, probability, lag, n_observed=108,
                                                     funded_nav=representation == 'funded')
                            _, after_flags = evaluate(ledger['reported_returns'], context, representation, 108)
                            for row in summaries(before_flags, after_flags, ledger):
                                rows.append({'weighting': context['weighting'], 'representation': representation,
                                             'policy': policy, 'delta': delta, 'lag': lag_name(lag),
                                             'method': row['method'], 'draw': draw, 'n_strategies': row['n_strategies'],
                                             'changed_paths': row['changed_paths'],
                                             **{column: row[column] for column in RATE_COLUMNS}})
    output = []
    grouping = ['weighting', 'representation', 'policy', 'delta', 'lag', 'method']
    for key, group in pd.DataFrame(rows).groupby(grouping, sort=True):
        record = dict(zip(grouping, key))
        record.update(policy_draws=draws, months=108, n_strategies=int(group['n_strategies'].iloc[0]),
                      mean_changed_paths=float(group['changed_paths'].mean()),
                      min_changed_paths=int(group['changed_paths'].min()),
                      max_changed_paths=int(group['changed_paths'].max()),
                      uncertainty='policy MCSE conditional on fixed observed histories')
        for column in RATE_COLUMNS:
            valid = group[column].dropna()
            record[f'{column}_mean'] = float(valid.mean()) if len(valid) else np.nan
            record[f'{column}_mcse'] = float(valid.std(ddof=1) / np.sqrt(len(valid))) if len(valid) > 1 else np.nan
            record[f'{column}_valid_draws'] = len(valid)
        output.append(record)
    return pd.DataFrame(output)


def bootstrap_ranges(contexts, design):
    draws = design['bootstrap']['power_interval_draws']
    rng = np.random.default_rng(np.random.SeedSequence([design['seed'], 9, 4]))
    indices = circular_indices(rng, draws, 114, 108, 12)
    rows = []
    for draw, months_index in enumerate(indices):
        for context in contexts:
            spread = context['spread'][:, 6:][:, months_index]
            rf = context['rf'][6:][months_index]
            for representation in REPRESENTATIONS:
                values = basis_values(spread, rf, representation)
                _, before_flags = evaluate(values[:, 6:], context, representation, 108)
                prepared = prepare_ledger_inputs(values, pick_draws=np.zeros_like(values))
                for lag in LAGS:
                    ledger = transform_paths(prepared, .01, 1., lag, n_observed=108,
                                             funded_nav=representation == 'funded')
                    _, after_flags = evaluate(ledger['reported_returns'], context, representation, 108)
                    for row in summaries(before_flags, after_flags, ledger):
                        rows.append({'weighting': context['weighting'], 'representation': representation,
                                     'lag': lag_name(lag), 'method': row['method'], 'draw': draw,
                                     **{column: row[column] for column in RATE_COLUMNS}})
        if (draw + 1) % 100 == 0:
            print(json.dumps({'stage': 'reporting_bootstrap', 'draws_completed': draw + 1}), flush=True)
    output = []
    grouping = ['weighting', 'representation', 'lag', 'method']
    for key, group in pd.DataFrame(rows).groupby(grouping, sort=True):
        record = dict(zip(grouping, key))
        record.update(draws=draws, months=108, block_months=12, delta=.01, probability=1.,
                      uncertainty='joint calendar-block conditional percentile range')
        for column in RATE_COLUMNS:
            valid = group[column].dropna()
            record[f'{column}_mean'] = float(valid.mean()) if len(valid) else np.nan
            record[f'{column}_lo'] = float(valid.quantile(.025)) if len(valid) else np.nan
            record[f'{column}_hi'] = float(valid.quantile(.975)) if len(valid) else np.nan
        output.append(record)
    return pd.DataFrame(output)


def save_csv(frame, destination):
    temporary = destination.with_suffix('.csv.tmp')
    frame.to_csv(temporary, index=False)
    temporary.replace(destination)


def main():
    started = time.monotonic()
    design = read_design()
    contexts, dependencies = load_contexts(design)
    for path in [ROOT / 'data/frozen_design.json', ROOT / 'scripts/a9_reporting.py',
                 ROOT / 'scripts/a9_metrics.py', ROOT / 'scripts/a9_data.py',
                 ROOT / 'scripts/run_benchmarks.py', Path(__file__)]:
        dependencies[str(path.relative_to(ROOT))] = file_hash(path)
    execution_path = ROOT / 'data/reporting_execution.json'
    if execution_path.is_file():
        old = json.loads(execution_path.read_text())
        if old.get('status') == 'complete':
            if old['dependencies'] != dependencies:
                raise RuntimeError('Completed reporting results have different dependencies')
            for name, expected in old['outputs'].items():
                if file_hash(ROOT / name) != expected:
                    raise RuntimeError('An existing completed reporting output differs from its hash')
            print('Reporting analysis already complete with matching dependencies and outputs.')
            return
    selection_self_check()
    common_names = sorted(set().union(*(context['names'] for context in contexts)))
    point_rng = np.random.default_rng(np.random.SeedSequence([design['seed'], 9, 1]))
    point_picks = point_rng.random((len(common_names), 114))
    metadata = {'status': 'running', 'dependencies': dependencies,
                'seed': design['seed'], 'seed_stages': {'fixed_point': 1, 'half_hiding': 2,
                                                      'uniform_target': 3, 'calendar_bootstrap': 4},
                'stage_prefix': 9, 'observed_window': ['2017-01', '2025-12'],
                'actual_warmup': ['2016-07', '2016-12'], 'supplied_economic_tail_months': 0,
                'future_recognition_audit': 'Scheduled repayments exhaust the closing gap; no future economic months are supplied.',
                'cohorts': {context['weighting']: len(context['names']) for context in contexts},
                'observed_60_month_window': ['2021-01', '2025-12'],
                'policy_sensitivity_draws': design['reporting']['probability_sensitivity_draws'],
                'joint_calendar_draws': design['bootstrap']['power_interval_draws'],
                'selection_combinatorics_exhaustively_checked': True,
                'interpretation': 'Alerts on reconstructed and deliberately altered payoffs; real-fund fraud labels are unavailable.'}
    execution_path.write_text(json.dumps(metadata, indent=2) + '\n')
    point, selected, smoothing = point_analysis(contexts, point_picks, common_names)
    print(json.dumps({'stage': 'reporting_point_complete', 'rows': len(point)}), flush=True)
    sensitivity = policy_sensitivity(contexts, design, common_names)
    print(json.dumps({'stage': 'reporting_policy_sensitivity_complete', 'rows': len(sensitivity)}), flush=True)
    ranges = bootstrap_ranges(contexts, design)
    outputs = {'reporting_point.csv': point, 'reporting_selection.csv': selected,
               'smoothing_sensitivity.csv': smoothing, 'reporting_sensitivity.csv': sensitivity,
               'reporting_bootstrap_ranges.csv': ranges}
    for name, frame in outputs.items():
        save_csv(frame, ROOT / 'tables' / name)
    for name, expected in dependencies.items():
        if file_hash(ROOT / name) != expected:
            raise RuntimeError(f'Frozen reporting dependency changed during execution: {name}')
    metadata.update(status='complete', seconds=time.monotonic() - started,
                    maximum_point_ledger_error=float(point['ledger_max_error'].max()),
                    maximum_scheduled_settlement_error=float(point['scheduled_settlement_error'].max()),
                    outputs={f'tables/{name}': file_hash(ROOT / 'tables' / name) for name in outputs},
                    output_rows={name: len(frame) for name, frame in outputs.items()})
    execution_path.write_text(json.dumps(metadata, indent=2) + '\n')
    print(json.dumps({'status': 'complete', 'seconds': metadata['seconds'], 'rows': metadata['output_rows']}), flush=True)


if __name__ == '__main__':
    main()
