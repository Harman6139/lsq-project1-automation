"""Compare the 38 frozen screening arrangements across all ten reporting changes."""
from pathlib import Path
import json
from hashlib import sha256

import numpy as np
import pandas as pd

from frontier_engine import (
    ROOT, apply_policy, dependency_hashes, design, get_maps, inputs,
    observed_window, performance_groups, warning_statistics,
)
from frontier_metrics import combine_scores, rank_scores, raw_scores


ORIGINAL = 'OR:B+D'
PAIR = 'OR:A+Z'
TRIO = 'OR:B+A+Z'
LABELS = {
    'relative_permanent': 'Leave out small losses',
    'relative_delay1': 'Delay 1 month',
    'relative_delay3': 'Delay 3 months',
    'relative_delay6': 'Delay 6 months',
    'relative_half_delay3': 'Delay 3 months, half applied',
    'fixed_permanent': 'Leave out losses up to 1%',
    'fixed_delay3': 'Delay losses up to 1%',
    'smooth25': 'Average, 25% previous month',
    'smooth50': 'Average, 50% previous month',
    'smooth75': 'Average, 75% previous month',
}
METRICS = ['n', 'changed', 'baseline', 'altered', 'new', 'cleared']
KEYS = ['group', 'mechanism', 'policy', 'budget']


def read_frozen(name):
    data = pd.read_csv(ROOT / f'tables/{name}_original.csv', float_precision='round_trip')
    return data[(data.representation == 'spread') & (data.months == 108) & (data.end == '2025-12')]


def extend_curves(spec):
    panel, rf = inputs('original', spec['core_signals'])
    frozen = pd.read_csv(ROOT / 'tables/cutoffs_original.csv', float_precision='round_trip')
    frozen = frozen[(frozen.representation == 'spread') & (frozen.months == 108) & (frozen.block == 12)]
    policies = [p['id'] for p in spec['policies']]
    cutoffs = frozen.pivot(index='policy', columns='budget', values='cutoff').loc[policies].to_numpy()
    cache = ROOT / 'data/cache/original_spread_108_b12'
    if cache.with_suffix('.npz').exists():
        meta = json.loads(cache.with_suffix('.json').read_text())
        assert meta['settings']['dependencies'] == dependency_hashes()
        with np.load(cache.with_suffix('.npz')) as saved:
            maps = [saved[f'map{j}'] for j in range(4)]
            np.testing.assert_array_equal(cutoffs, saved['cutoffs'])
        pca = meta['pca']
    else:
        maps, _ = get_maps(panel, rf, 108, 'spread', spec['development'])
        # The PCA weights are frozen as part of the existing reference fit.
        meta = json.loads((ROOT / 'data/frozen_primary_pca.json').read_text())
        assert meta['dependencies'] == dependency_hashes()
        pca = meta['pca']
    full, h = observed_window(panel, rf, '2025-12', 108, 'spread')
    groups = performance_groups(h)
    picks = np.random.default_rng(np.random.SeedSequence([spec['seed'], 3, 108, 2025])).random(full.shape)

    def score(x):
        return combine_scores(rank_scores(raw_scores(x)[0], maps), spec['policies'], pca)

    base = score(full[:, 6:])
    result = []
    for policy in spec['reporting_policies']:
        edited, changed, _ = apply_policy(full, policy, 108, picks=picks, funded=False)
        rows = warning_statistics(base, score(edited), changed, cutoffs, range(101), groups)
        result.extend(dict(mechanism=policy['id'], **r) for r in rows)
    return pd.DataFrame(result)


def verify_overlap(curves, saved):
    saved = saved[saved.mechanism.isin(LABELS)]
    check = saved[KEYS + METRICS].merge(curves[KEYS + METRICS], on=KEYS,
        how='left', validate='one_to_one', suffixes=('_saved', '_replay'))
    assert len(check) == len(saved)
    for col in METRICS:
        np.testing.assert_array_equal(check[f'{col}_saved'], check[f'{col}_replay'])
    return len(check)


def matched(curves):
    rows = []
    for (group, mechanism, policy), block in curves.groupby(['group', 'mechanism', 'policy'], sort=False):
        ordered = block.sort_values('budget')
        baseline = ordered.baseline.to_numpy()
        altered = ordered.altered.to_numpy()
        assert (np.diff(baseline) >= 0).all()
        assert (np.diff(altered) >= 0).all()
        caps = np.arange(int(ordered.n.iloc[0]) + 1)
        feasible = np.searchsorted(baseline, caps, side='right') - 1
        best = np.searchsorted(altered, altered[feasible], side='left')
        rows.append(pd.DataFrame(dict(group=group, mechanism=mechanism,
            policy=policy, cap=caps, baseline=baseline[best], altered=altered[best],
            new=ordered.new.to_numpy()[best], budget=ordered.budget.to_numpy()[best])))
    return pd.concat(rows, ignore_index=True)


def main():
    spec = design()
    order = [p['id'] for p in spec['policies']]
    choices = pd.read_csv(ROOT / 'tables/policy_choices_original.csv', float_precision='round_trip')
    choices = choices[(choices.representation == 'spread') & (choices.months == 108) &
                     (choices.budget == .05) & (choices.left_out == 'none')]
    curves = extend_curves(spec)
    saved = read_frozen('point_rates')
    checked_points = verify_overlap(curves, saved)
    checked_curves = verify_overlap(curves, read_frozen('frontier_curves'))
    assert len(curves) == 38 * 10 * 101 * 3
    point = saved[saved.mechanism.isin(LABELS)].copy()
    for benchmark, tag in [(ORIGINAL, 'original_pair'), (PAIR, 'new_pair')]:
        cols = ['group', 'mechanism', 'budget']
        other = point[point.policy == benchmark][cols + ['baseline', 'altered', 'new']]
        point = point.merge(other.rename(columns={m:f'{m}_{tag}' for m in ['baseline','altered','new']}),
                           on=cols, validate='many_to_one')
        for col in ['baseline','altered','new']:
            point[f'{col}_minus_{tag}'] = point[col] - point[f'{col}_{tag}']
    point['reporting_change'] = point.mechanism.map(LABELS)
    point.to_csv(ROOT / 'tables/all_reporting_comparison.csv', index=False)

    # Each line in this output is the best observed point for one rule, edit and cap.
    capped = matched(curves)
    capped[capped.cap.le(20)].to_csv(ROOT/'tables/all_reporting_named_frontiers.csv', index=False)
    comparison = capped[capped.cap.isin([0,1,2,3,4,5,10,20])].copy()
    for benchmark, tag in [(ORIGINAL, 'original_pair'), (PAIR, 'new_pair')]:
        cols = ['group','mechanism','cap']
        other = comparison[comparison.policy==benchmark][cols+['altered']]
        comparison = comparison.merge(other.rename(columns={'altered':f'altered_{tag}'}), on=cols, validate='many_to_one')
        comparison[f'altered_minus_{tag}'] = comparison.altered - comparison[f'altered_{tag}']
    envelopes = capped.groupby(['group','mechanism','cap'], sort=False).altered.max().rename('all_rules_max').reset_index()
    for benchmark, tag in [(ORIGINAL, 'original_pair'), (PAIR, 'new_pair')]:
        other = capped[capped.policy==benchmark][['group','mechanism','cap','altered']]
        envelopes = envelopes.merge(other.rename(columns={'altered':tag}), on=['group','mechanism','cap'], validate='one_to_one')
    envelopes.to_csv(ROOT / 'tables/all_reporting_frontiers.csv', index=False)
    comparison.to_csv(ROOT / 'tables/all_reporting_matched_counts.csv', index=False)

    # Each cross-edit average uses the SAME rule and SAME cutoff for all ten edits.
    combined = curves.groupby(['group','policy','budget'],sort=False).agg(
        baseline=('baseline','first'), baseline_max=('baseline','max'),
        mean_altered=('altered','mean'), min_altered=('altered','min'),
        mean_new=('new','mean')).reset_index()
    assert (combined.baseline == combined.baseline_max).all()
    joint_at_caps = {}
    for group in ['all', 'top_quintile']:
        joint_at_caps[group] = {}
        for cap in [0, 1, 3, 5, 10]:
            v = combined[(combined.group == group) & (combined.baseline <= cap)]
            row = v.sort_values(['mean_altered','baseline','budget','policy'], ascending=[False,True,True,True]).iloc[0]
            col = v.sort_values(['min_altered','baseline','budget','policy'], ascending=[False,True,True,True]).iloc[0]
            joint_at_caps[group][cap] = dict(best_mean=row.to_dict(),best_worst=col.to_dict())
    combined.drop(columns='baseline_max').to_csv(ROOT / 'tables/all_reporting_joint_curves.csv',index=False)

    view = point[(point.group=='all') & (point.budget==.05)]
    grid = view.pivot(index='policy', columns='mechanism',values='altered').loc[order,list(LABELS)]
    summary = grid.agg(['mean','min'],axis=1).rename(columns={'mean':'mean_altered','min':'min_altered'})
    summary['baseline'] = view.groupby('policy').baseline.first()
    summary['first_or_tied'] = grid.eq(grid.max()).sum(axis=1)
    summary['mean_new'] = view.groupby('policy').new.mean()
    summary = summary.join(view.groupby('policy').families.first()).sort_values('mean_altered',ascending=False)
    summary.to_csv(ROOT/'tables/all_reporting_summary.csv')
    cap3=capped[(capped.group=='all') & (capped.cap==3)].pivot(index='policy',columns='mechanism',values='altered').loc[order,list(LABELS)]
    top = point[(point.group=='top_quintile') & (point.budget==.05)]
    data=dict(
        verified_original_point_rows=checked_points, verified_original_curve_rows=checked_curves,
        evaluations=len(curves), joint_at_caps=joint_at_caps, historical_choices=choices[['scope','policy','training_new_warning_rate']].to_dict('records'),
        fixed_target=summary.loc[[ORIGINAL,PAIR,TRIO,'OR:B+D+A+Z','A','Z']].to_dict('index'),
        best_by_edit={m:dict(value=int(grid[m].max()),policies=grid.index[grid[m]==grid[m].max()].tolist()) for m in LABELS},
        cap3={m:dict(value=int(cap3[m].max()),policies=cap3.index[cap3[m]==cap3[m].max()].tolist(),
                      original=int(cap3.loc[ORIGINAL,m]),pair=int(cap3.loc[PAIR,m])) for m in LABELS},
        top_group=top.groupby('policy').agg(n=('n','first'),baseline=('baseline','first'),mean=('altered','mean'),
                                          worst=('altered','min')).loc[[ORIGINAL,PAIR,TRIO,'OR:B+D+A+Z','A','Z']].to_dict('index'),
        input_sha256={name:sha256((ROOT/name).read_bytes()).hexdigest() for name in [
            'data/frozen_design.json','tables/cutoffs_original.csv','tables/point_rates_original.csv','tables/frontier_curves_original.csv']},
    )
    (ROOT/'data/all_reporting_comparison.json').write_text(json.dumps(data,indent=2)+'\n',encoding='utf-8')
    print(summary.head(10).to_string())
    print(json.dumps(data,indent=2))


if __name__=='__main__':
    main()
