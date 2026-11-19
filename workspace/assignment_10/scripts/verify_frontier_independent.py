"""Independent scalar checks for the frozen frontier computation.

Unit cases use explicit loops and scalar probability/ledger identities. They do
not inspect the empirical frontier outputs.
"""

from fractions import Fraction
from hashlib import sha256
from itertools import product
from math import erfc, expm1, fsum, isclose, log1p, sqrt
from pathlib import Path
import argparse
import json

import numpy as np

from frontier_engine import apply_policy, calendar_indices
from frontier_metrics import (combine_scores, conservative_cutoffs, fit_maps,
                              fit_pca, policy_specs, rank_scores, raw_scores)

ROOT = Path(__file__).resolve().parents[1]


def scalar_scores(values, bandwidth):
    row = [float(value) for value in values]
    n = len(row)
    mean = fsum(row) / n
    centered = [value - mean for value in row]
    squares = fsum(value * value for value in centered)
    sd = sqrt(squares / (n - 1))
    upper = sum(0 <= value <= sd for value in row)
    lower = sum(-sd <= value < 0 for value in row)
    losses = sum(value < 0 for value in row)
    band = bandwidth * sd
    l1 = sum(-band <= value < 0 for value in row)
    l2 = sum(-2 * band <= value < -band for value in row)
    g1 = sum(0 < value <= band for value in row)
    g2 = sum(band < value <= 2 * band for value in row)
    variance_proxy = 9 * (g1 + l1) + g2 + l2
    local = (3 * (g1 - l1) - (g2 - l2)) / sqrt(variance_proxy) if variance_proxy else 0.
    expected = [upper / (1 + lower), n * .5 * erfc(mean / (sd * sqrt(2))) - losses,
                fsum(centered[t] * centered[t - 1] for t in range(1, n)) / squares, local]
    details = dict(mean=mean, sd=sd, h=mean / sd, negative=losses, upper=upper,
                   lower=lower, exact_zeros=sum(value == 0 for value in row),
                   local_l1=l1, local_l2=l2, local_g1=g1, local_g2=g2)
    return expected, details


def check_metrics():
    rng = np.random.default_rng(2026111901)
    rows = rng.normal(.002, .03, size=(12, 108))
    rows[0, :8] = [-.02, 0., .0001, -.0001, .01, -.01, .03, .08]
    comparisons = 0
    for bandwidth in (.25, .5):
        actual, details = raw_scores(rows.reshape(3, 4, 108), bandwidth)
        for i, row in enumerate(rows):
            expected, scalar_details = scalar_scores(row, bandwidth)
            np.testing.assert_allclose(actual.reshape(-1, 4)[i], expected, rtol=1e-12, atol=1e-12)
            for key, value in scalar_details.items():
                np.testing.assert_allclose(details[key].reshape(-1)[i], value, rtol=1e-12, atol=1e-12)
            comparisons += 1
        scaled, _ = raw_scores(rows * 8, bandwidth)
        np.testing.assert_allclose(scaled, actual.reshape(-1, 4), rtol=1e-12, atol=1e-12)
    endpoints = np.array([[-2., -1., 0., 1., 2.]])
    _, endpoint_counts = raw_scores(endpoints, 1 / sqrt(2.5))
    for key in ('local_l1', 'local_l2', 'local_g1', 'local_g2'):
        assert endpoint_counts[key][0] == 1, key
    assert endpoint_counts['exact_zeros'][0] == 1
    empty_band, _ = raw_scores(np.array([[-1., 0., 0., 1.]]))
    assert empty_band[0, 3] == 0
    for invalid in (np.ones((1, 5)), np.array([[0., 1., np.nan, 2.]]), np.arange(5.)):
        try:
            raw_scores(invalid)
        except ValueError:
            continue
        raise AssertionError('An invalid metric input was accepted')
    return dict(scalar_metric_paths=comparisons, scalar_detail_counts_match=True,
                local_band_endpoints_match=True, zero_and_empty_band_conventions_match=True,
                positive_scale_invariance=True, invalid_metric_inputs_rejected=True)


def check_combinations():
    specs = policy_specs()
    primary = [spec for spec in specs if spec['primary']]
    assert len(specs) == 38 and len(primary) == 26
    assert len({spec['id'] for spec in specs}) == 38
    assert len(policy_specs(False)) == 26
    ranks = np.array(list(product((0., .25, .5, .75, 1.), repeat=4)))
    scores = combine_scores(ranks, primary)
    comparisons = 0
    for i, row in enumerate(ranks):
        for j, spec in enumerate(primary):
            for threshold in (0., .25, .5, .75, 1.):
                votes = sum(row[index] > threshold for index in spec['indices'])
                expected = votes >= 1 if spec['aggregation'] == 'any' else 2 * votes > spec['count']
                assert (scores[i, j] > threshold) == expected
                comparisons += 1
    return dict(total_policies=38, primary_policies=26, boolean_vote_comparisons=comparisons,
                or_and_strict_majority_equivalence=True)


def scalar_policy(values, policy, months, warmup, picks, funded):
    flat = np.asarray(values).reshape(-1, values.shape[-1])
    pick_flat = np.asarray(picks).reshape(flat.shape)
    expected, closing_gaps, terminal_gaps = [], [], []
    maximum_identity_error = 0.
    stop = warmup + months
    for i, row in enumerate(flat):
        if policy['kind'] == 'smoothing':
            weight = policy['weight']
            observed = [(1 - weight) * row[t] + weight * row[t - 1] for t in range(warmup, stop)]
            expected.append(observed)
            identity = fsum(observed) - fsum(float(value) for value in row[warmup:stop])
            np.testing.assert_allclose(identity, weight * (row[warmup - 1] - row[stop - 1]), atol=1e-14)
            continue
        sample = row[warmup:stop]
        mean = fsum(float(value) for value in sample) / months
        sd = sqrt(fsum((float(value) - mean) ** 2 for value in sample) / (months - 1))
        bound = policy['bound'] * (sd if policy['scale'] == 'sd' else 1.)
        target = policy['gain'] * (sd if policy['scale'] == 'sd' else 1.)
        lag = policy['lag']
        schedule = {}
        output = []
        coordinates = []
        gap = opening = closing = 0.
        for t, value in enumerate(row):
            coordinate = log1p(float(value)) if funded else float(value)
            coordinates.append(coordinate)
            recognised = schedule.pop(t, 0.)
            hidden = 0.
            if t < stop and -bound <= value < 0 and (policy['p'] == 1 or pick_flat[i, t] < policy['p']):
                hidden = (log1p(target) if funded else target) - coordinate
                if lag != 'permanent':
                    schedule[t + lag] = schedule.get(t + lag, 0.) + hidden
            gap += hidden - recognised
            output.append(coordinate + hidden - recognised)
            if t == warmup - 1:
                opening = gap
            if t == stop - 1:
                closing = gap
        excess = fsum(output[warmup:stop]) - fsum(coordinates[warmup:stop])
        maximum_identity_error = max(maximum_identity_error, abs(excess - closing + opening))
        if lag != 'permanent':
            np.testing.assert_allclose(gap, sum(schedule.values()), atol=1e-14)
            if len(row) >= stop + lag:
                np.testing.assert_allclose(gap, 0., atol=1e-14)
        observed = output[warmup:stop]
        expected.append([expm1(value) for value in observed] if funded else observed)
        closing_gaps.append(closing)
        terminal_gaps.append(gap)
    return np.array(expected).reshape(values.shape[:-1] + (months,)), closing_gaps, terminal_gaps, maximum_identity_error


def check_reporting(frozen):
    rng = np.random.default_rng(2026111902)
    full = rng.normal(.001, .012, size=(2, 3, 120))
    full[..., :7] = [-.01, 0., -.005, .02, -.02, -.001, -.01]
    picks = rng.random(full.shape)
    cases = 0
    maximum_identity_error = 0.
    for months in (60, 108):
        supplied = full[..., :months + 12]
        for funded in (False, True):
            for policy in frozen['reporting_policies']:
                actual, changed, ledger = apply_policy(supplied, policy, months,
                                                       picks=picks[..., :months + 12], funded=funded)
                expected, closing, terminal, error = scalar_policy(supplied, policy, months, 6,
                                                                   picks[..., :months + 12], funded)
                np.testing.assert_allclose(actual, expected, rtol=1e-12, atol=1e-14)
                expected_changed = np.any(np.abs(expected - supplied[..., 6:6 + months]) > 1e-14, axis=-1)
                assert np.array_equal(changed, expected_changed)
                if policy['kind'] != 'smoothing':
                    np.testing.assert_allclose(ledger['closing_gap'], np.mean(closing), atol=1e-14)
                if not funded and (policy['kind'] == 'smoothing' or policy['scale'] == 'sd'):
                    scaled, scaled_changed, _ = apply_policy(supplied * 8, policy, months,
                                                              picks=picks[..., :months + 12])
                    np.testing.assert_allclose(scaled, actual * 8, rtol=1e-12, atol=1e-13)
                    assert np.array_equal(scaled_changed, changed)
                maximum_identity_error = max(maximum_identity_error, error, ledger['max_error'])
                cases += 1
        # Economic returns supplied beyond the observation boundary cannot
        # change the observed record or the central-window eligibility scale.
        other_tail = supplied.copy()
        other_tail[..., months + 6:] += .1
        policy = next(p for p in frozen['reporting_policies'] if p['id'] == 'relative_delay6')
        observed, _, _ = apply_policy(supplied, policy, months)
        altered_tail, _, _ = apply_policy(other_tail, policy, months)
        assert np.array_equal(observed, altered_tail)
    partial = np.array([[-.01, .01, -.003, .01, 0., -.005, .01, .01, -.005, .01]])
    policy = dict(kind='loss', scale='fixed', bound=.01, gain=.0005, lag=6, p=1.)
    actual, _, ledger = apply_policy(partial, policy, months=4, warmup=6)
    expected, closing, terminal, error = scalar_policy(partial, policy, 4, 6, np.zeros_like(partial), False)
    np.testing.assert_allclose(actual, expected, atol=1e-14)
    assert closing[0] > 0 and terminal[0] > 0
    np.testing.assert_allclose(ledger['closing_gap'], closing[0], atol=1e-14)
    invalid_funded = partial.copy()
    invalid_funded[0, 7] = -1.2
    apply_policy(invalid_funded, policy, months=4, warmup=6, funded=False)
    try:
        apply_policy(invalid_funded, policy, months=4, warmup=6, funded=True)
    except ValueError:
        pass
    else:
        raise AssertionError('An invalid funded NAV was accepted')
    return dict(policy_batch_cases=cases, scalar_scheduler_matches=True,
                relative_and_fixed_eligibility_match=True, probability_half_matches=True,
                additive_and_funded_log_ledgers_match=True, supplied_tail_settlement_matches=True,
                relative_payoff_policy_scale_invariance=True, funded_nav_support_guard_matches=True,
                pending_after_window_balances_match=True, supplied_future_payoffs_do_not_change_observed_window=True,
                maximum_ledger_identity_error=maximum_identity_error)


def check_maps_pca_and_cutoffs():
    rng = np.random.default_rng(2026111903)
    development = rng.normal(size=(6, 9, 4))
    development[0, :, 0] = 0.
    maps = fit_maps(development)
    evaluation = np.vstack([development[0], [-100., 100., 0., .1]])
    ranks = rank_scores(evaluation, maps)
    for i, row in enumerate(evaluation):
        for j in range(4):
            reference = [float(value[j]) for group in development for value in group]
            np.testing.assert_allclose(ranks[i, j], sum(value <= row[j] for value in reference) / (len(reference) + 1), atol=1e-15)
    pca_data = rng.normal(size=(600, 4)) @ np.array([[1., .2, .5, -.1], [.1, 1., .2, .4], [.5, .2, 1., .2], [.2, .5, .1, 1.]])
    pca = fit_pca(pca_data)
    means = np.array([fsum(float(row[j]) for row in pca_data) / len(pca_data) for j in range(4)])
    sds = np.array([sqrt(fsum((float(row[j]) - means[j]) ** 2 for row in pca_data) / (len(pca_data) - 1)) for j in range(4)])
    standardized = (pca_data - means) / sds
    _, _, right = np.linalg.svd(standardized, full_matrices=False)
    weights = right[0]
    if weights.sum() < 0:
        weights = -weights
    np.testing.assert_allclose(pca['mean'], means, atol=1e-14)
    np.testing.assert_allclose(pca['sd'], sds, atol=1e-14)
    np.testing.assert_allclose(pca['weights'], weights, atol=1e-12)
    specs = policy_specs()
    scores = combine_scores(ranks, specs, pca)
    for i, row in enumerate(ranks):
        for j, spec in enumerate(specs):
            if spec['aggregation'] == 'mean':
                expected = fsum(float(row[index]) for index in spec['indices']) / spec['count']
                np.testing.assert_allclose(scores[i, j], expected, atol=1e-15)
            elif spec['aggregation'] == 'pca':
                expected = fsum((float(row[k]) - means[k]) / sds[k] * weights[k] for k in range(4))
                np.testing.assert_allclose(scores[i, j], expected, atol=1e-12)
    values = np.array([0., 0., .25, .5, .5, .75, 1., 1.])
    budgets = np.array([0., .01, .05, .1, .2, .25, .375, .5, .625, .75, .875, 1.])
    weight_cases = [None, np.array([0., 1., 2., 0., 3., 1., 1., 0.]),
                    np.array([.25, 0., 0., .25, .25, .25, 0., 0.])]
    checked = 0
    for weights_case in weight_cases:
        weights_array = np.ones(len(values)) if weights_case is None else weights_case
        cutoffs = conservative_cutoffs(values, budgets, weights_case)
        assert np.isposinf(cutoffs[0]) and np.isneginf(cutoffs[-1])
        assert np.all(cutoffs[1:] <= cutoffs[:-1])
        for budget, cutoff in zip(budgets, cutoffs):
            actual_mass = fsum(float(w) for value, w in zip(values, weights_array) if value > cutoff) / fsum(weights_array)
            assert actual_mass <= budget + 1e-14
            if budget not in (0., 1.):
                assert cutoff in values
                feasible = [candidate for candidate in sorted(set(values))
                            if fsum(float(w) for value, w in zip(values, weights_array) if value > candidate)
                            <= budget * fsum(weights_array) + 1e-14]
                assert cutoff >= min(feasible)
            checked += 1
    all_tied = conservative_cutoffs(np.ones(20), np.array([0., .01, .05, .1, .2, 1.]))
    assert np.all(all_tied[1:-1] == 1.)
    return dict(scalar_percentile_ties_match=True, pca_matches_independent_svd=True,
                mean_rank_comparators_match=True, weighted_budget_cases=checked,
                strict_warning_budgets_respected=True, budget_boundary_and_all_tie_cases_match=True)


def check_calendar_indices():
    seed = 2026111904
    rng = np.random.default_rng(seed)
    actual = calendar_indices(rng, 4, 17, 23, 6)
    starts = np.random.default_rng(seed).integers(0, 23, size=(4, 3))
    expected = np.array([[int(starts[i, block]) + within for block in range(3) for within in range(6)]
                         for i in range(4)])[:, :17] % 23
    assert np.array_equal(actual, expected)
    warm_source = np.arange(-6, 23)
    for first in range(23):
        previous = warm_source[first + np.arange(6)]
        assert np.array_equal(previous, np.arange(first - 6, first))
    return dict(circular_blocks_match_scalar_indices=True, actual_six_month_pre_history_indexing_matches=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--core-only', action='store_true')
    args = parser.parse_args()
    frozen = json.loads((ROOT / 'data/frozen_design.json').read_text())
    checks = {'metrics': check_metrics(), 'combinations': check_combinations(),
              'reporting': check_reporting(frozen)}
    if not args.core_only:
        checks['maps_pca_cutoffs'] = check_maps_pca_and_cutoffs()
        checks['calendar_indices'] = check_calendar_indices()
    dependencies = {str(path.relative_to(ROOT)): sha256(path.read_bytes()).hexdigest()
                    for path in [ROOT / 'scripts/frontier_metrics.py', ROOT / 'scripts/frontier_engine.py',
                                 ROOT / 'data/frozen_design.json']}
    target = ROOT / 'data/independent_verification.json'
    existing = json.loads(target.read_text()) if target.exists() else {}
    existing['scalar_checks'] = {'status': 'core_passed' if args.core_only else 'passed',
                                 'dependencies': dependencies, **checks}
    temporary = target.with_suffix('.json.tmp')
    temporary.write_text(json.dumps(existing, indent=2) + '\n')
    temporary.replace(target)
    print(json.dumps(existing['scalar_checks'], indent=2))


if __name__ == '__main__':
    main()
