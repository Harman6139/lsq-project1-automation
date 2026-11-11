"""Reporting changes for observed long-short payoffs and explicitly funded NAVs.

The default ledger conserves additive long-short P&L. An eligible underlying
loss is initially replaced by a small gain and recognised after a fixed delay.
The funded helper instead conserves cumulative log NAV and requires an explicit
funded-return input. Each method tracks the gap carried into and out of the
observation window. Repayments are determined by their original due dates.
"""

from __future__ import annotations

from collections.abc import Mapping
from numbers import Integral
from typing import Any

import numpy as np

MAX_TARGET_GAIN = 0.001
DEFAULT_TARGET_GAIN = 0.0005


def _path_array(values: Any) -> np.ndarray:
    array = np.asarray(values, dtype=np.float64)
    if array.ndim == 1:
        array = array[None, :]
    if array.ndim != 2 or min(array.shape) < 1 or not np.isfinite(array).all():
        raise ValueError('Returns must be a finite nonempty path-by-month array')
    return array


def _draw_array(values: Any, shape: tuple[int, int], name: str,
                maximum: float) -> np.ndarray:
    array = np.asarray(values, dtype=np.float64)
    if array.ndim == 1 and shape[0] == 1:
        array = array[None, :]
    if array.shape != shape or not np.isfinite(array).all():
        raise ValueError(f'{name} must have finite values and shape {shape}')
    if np.any(array < 0.0) or np.any(array > maximum):
        raise ValueError(f'{name} must lie in [0, {maximum}]')
    return array


def prepare_ledger_inputs(r: Any, rng: np.random.Generator | None = None,
                          target_draws: Any = None, pick_draws: Any = None,
                          target_gain: float | None = DEFAULT_TARGET_GAIN
                          ) -> dict[str, np.ndarray]:
    """Prepare common reporting draws once for paired policy comparisons.

    The default target is the fixed simple gain 0.0005. Passing ``target_gain=None``
    draws uniform targets in [0, 0.001]. Explicit ``target_draws`` take precedence.
    Pick draws are uniforms in [0, 1]. Reuse the returned mapping across hiding
    probabilities and delays. This function reads inputs without modifying them.
    """
    underlying = _path_array(r)
    if target_draws is not None:
        target = _draw_array(target_draws, underlying.shape, 'target_draws', MAX_TARGET_GAIN)
    elif target_gain is None:
        if rng is None:
            raise ValueError('An rng is required for uniform target gains')
        target = rng.uniform(0.0, MAX_TARGET_GAIN, size=underlying.shape)
    else:
        if not np.isfinite(target_gain) or not 0.0 <= target_gain <= MAX_TARGET_GAIN:
            raise ValueError('target_gain must lie in [0, 0.001]')
        target = np.full_like(underlying, float(target_gain))
    if pick_draws is None:
        if rng is None:
            raise ValueError('Supply an rng or explicit common pick_draws')
        pick = rng.random(underlying.shape)
    else:
        pick = _draw_array(pick_draws, underlying.shape, 'pick_draws', 1.0)
    return {'underlying_returns': underlying, 'target_gain': target, 'pick_draws': pick}


def _window(length: int, warmup: int, n_observed: int) -> tuple[int, int]:
    if isinstance(warmup, bool) or not isinstance(warmup, Integral) or warmup < 0:
        raise ValueError('warmup must be a nonnegative integer')
    if isinstance(n_observed, bool) or not isinstance(n_observed, Integral) or n_observed < 1:
        raise ValueError('n_observed must be a positive integer')
    start, stop = int(warmup), int(warmup + n_observed)
    if stop > length:
        raise ValueError('Input paths do not contain the complete observation window')
    return start, stop


def _balance(q: np.ndarray, boundary: int, lag: int | None) -> np.ndarray:
    """Outstanding gap immediately before the month indexed by boundary."""
    first = 0 if lag is None else max(0, boundary - lag)
    return q[:, first:boundary].sum(axis=1)


def _future_recognitions(q: np.ndarray, boundary: int,
                         lag: int | None) -> np.ndarray:
    """Scheduled amounts for months boundary through boundary+lag-1."""
    if lag is None:
        return np.empty((q.shape[0], 0), dtype=np.float64)
    scheduled = np.zeros((q.shape[0], lag), dtype=np.float64)
    first = max(0, boundary - lag)
    source_months = np.arange(first, min(boundary, q.shape[1]))
    scheduled[:, source_months + lag - boundary] = q[:, source_months]
    return scheduled


def transform_paths(r: Any, delta: float, probability: float, lag: int | str | None,
                    rng: np.random.Generator | None = None,
                    warmup: int = 6, n_observed: int = 108,
                    target_draws: Any = None, pick_draws: Any = None,
                    return_full: bool = False,
                    target_gain: float | None = DEFAULT_TARGET_GAIN,
                    *, funded_nav: bool = False) -> dict[str, Any]:
    """Apply permanent concealment or delayed recognition to supplied paths.

    Eligibility is ``-delta <= underlying_return < 0``. In the additive ledger,
    q = target - underlying_return and reported = underlying + q - lagged(q).
    ``lag=None`` or ``'permanent'`` omits recognition. Recognition is based on
    underlying eligibility, so an incoming recognition amount cannot be re-hidden.

    Hiding operates during the supplied warm-up and screened window. It stops
    at the window boundary. A provided tail checks settlement on those actual
    input months. Remaining scheduled amounts are returned separately for audit.
    Only the central ``n_observed`` months are returned for screening.

    ``funded_nav=True`` expects funded simple returns already constructed by the
    caller, for example RF + LS under a declared cash-collateral convention. Its
    q increments and gaps are log-NAV quantities. The additive and log-NAV gap
    units are explicitly identified in the output.
    """
    if not np.isfinite(delta) or delta < 0.0:
        raise ValueError('delta must be finite and nonnegative')
    if not np.isfinite(probability) or not 0.0 <= probability <= 1.0:
        raise ValueError('probability must lie in [0, 1]')
    if lag is None or lag == 'permanent':
        release_lag = None
    elif isinstance(lag, Integral) and not isinstance(lag, bool) and lag > 0:
        release_lag = int(lag)
    else:
        raise ValueError('lag must be a positive integer, None or permanent')

    if isinstance(r, Mapping):
        if target_draws is not None or pick_draws is not None:
            raise ValueError('Prepared mappings already contain their common draws')
        underlying = _path_array(r['underlying_returns'])
        target = _draw_array(r['target_gain'], underlying.shape, 'target_gain', MAX_TARGET_GAIN)
        pick = _draw_array(r['pick_draws'], underlying.shape, 'pick_draws', 1.0)
    else:
        # Deterministic zero/all hiding requires no random pick mechanism.
        if rng is None and pick_draws is None and probability in (0.0, 1.0):
            pick_draws = np.zeros_like(_path_array(r))
        prepared = prepare_ledger_inputs(r, rng, target_draws, pick_draws, target_gain)
        underlying = prepared['underlying_returns']
        target, pick = prepared['target_gain'], prepared['pick_draws']
    start, stop = _window(underlying.shape[1], warmup, n_observed)
    if funded_nav and np.any(underlying <= -1.0):
        raise ValueError('Funded NAV returns must all exceed -1')
    coordinate = np.log1p(underlying) if funded_nav else underlying
    target_coordinate = np.log1p(target) if funded_nav else target
    eligible = (underlying >= -delta) & (underlying < 0.0)
    selected = eligible & ((pick < probability) if probability < 1.0 else True)
    selected[:, stop:] = False
    q = np.where(selected, target_coordinate - coordinate, 0.0)
    reported_coordinate = coordinate + q
    if release_lag is not None and release_lag < underlying.shape[1]:
        reported_coordinate[:, release_lag:] -= q[:, :-release_lag]

    opening = _balance(q, start, release_lag)
    closing = _balance(q, stop, release_lag)
    terminal = _balance(q, underlying.shape[1], release_lag)
    excess_observed = (reported_coordinate[:, start:stop] - coordinate[:, start:stop]).sum(axis=1)
    error_window = excess_observed - (closing - opening)
    error_full = (reported_coordinate - coordinate).sum(axis=1) - terminal
    error_max = float(max(np.max(np.abs(error_window)), np.max(np.abs(error_full))))
    tolerance = 1e-12 * max(1.0, float(np.max(np.abs(q).sum(axis=1))))
    if error_max > tolerance:
        raise ArithmeticError(f'Reporting ledger failed reconciliation with error {error_max}')
    with np.errstate(over='raise', invalid='raise'):
        reported = np.expm1(reported_coordinate) if funded_nav else reported_coordinate
    if not np.isfinite(reported).all():
        raise ArithmeticError('Reported values must be finite')
    observed = reported[:, start:stop]
    hidden_observed = q[:, start:stop].sum(axis=1)
    accounting = 'funded_log_nav' if funded_nav else 'additive_long_short_pnl'
    return {
        'accounting': accounting,
        'gap_units': 'log_nav_ratio' if funded_nav else 'payoff_per_unit_notional',
        'reported_returns': observed,
        'r_reported': observed,
        'full_reported_returns': reported if return_full else None,
        'full_reported_coordinate': reported_coordinate if return_full else None,
        'hidden_increments': q if return_full else None,
        'opening_gap': opening, 'closing_gap': closing, 'terminal_gap': terminal,
        'excess_observed_coordinate': excess_observed,
        'hidden_events': selected[:, start:stop].sum(axis=1),
        'hidden_events_total': selected.sum(axis=1),
        'hidden_observed_amount': hidden_observed,
        'recognised_observed_amount': hidden_observed + opening - closing,
        'scheduled_recognitions_after_window': _future_recognitions(q, stop, release_lag),
        'scheduled_recognitions_after_input': _future_recognitions(q, underlying.shape[1], release_lag),
        'tail_months_provided': underlying.shape[1] - stop,
        'settlement_tail_complete': bool(release_lag is not None and underlying.shape[1] >= stop + release_lag),
        'fully_settled': bool(release_lag is not None and np.all(np.abs(terminal) <= tolerance)),
        'has_observed_change': np.any(np.abs(observed - underlying[:, start:stop]) > 1e-14, axis=1),
        'ledger_max_error': error_max,
        'lag': release_lag, 'probability': float(probability), 'delta': float(delta),
        'warmup': start, 'n_observed': int(n_observed),
    }


def transform_funded_nav_paths(r: Any, delta: float, probability: float,
                               lag: int | str | None, **kwargs: Any) -> dict[str, Any]:
    """Apply the log-NAV ledger to an explicitly constructed funded-return book.

    Remaining options match ``transform_paths``. A raw long-short spread requires
    the caller's financing convention before entering this helper.
    """
    return transform_paths(r, delta, probability, lag, funded_nav=True, **kwargs)


def moving_average_paths(r: Any, smoothing: float, warmup: int = 6,
                         n_observed: int = 108, return_full: bool = False) -> dict[str, Any]:
    """Apply the causal filter (1-lambda)*r_t + lambda*r_(t-1) to both signs.

    This is a linear payoff-filter sensitivity with its own endpoint identity.
    The observation sum changes by lambda*(r_before_start-r_last_observed).
    """
    underlying = _path_array(r)
    if not np.isfinite(smoothing) or not 0.0 <= smoothing <= 1.0:
        raise ValueError('smoothing must lie in [0, 1]')
    start, stop = _window(underlying.shape[1], warmup, n_observed)
    if start < 1:
        raise ValueError('A preceding observed input month is required for the filter')
    reported = underlying.copy()
    reported[:, 1:] = (1.0 - smoothing) * underlying[:, 1:] + smoothing * underlying[:, :-1]
    difference = (reported[:, start:stop] - underlying[:, start:stop]).sum(axis=1)
    endpoint = smoothing * (underlying[:, start - 1] - underlying[:, stop - 1])
    error = float(np.max(np.abs(difference - endpoint)))
    if not np.allclose(difference, endpoint, rtol=1e-12, atol=1e-12):
        raise ArithmeticError('Moving-average endpoint identity failed')
    return {'accounting': 'linear_payoff_filter', 'reported_returns': reported[:, start:stop],
            'r_reported': reported[:, start:stop],
            'full_reported_returns': reported if return_full else None,
            'observation_sum_difference': difference, 'endpoint_sum_difference': endpoint,
            'filter_identity_error': error, 'smoothing': float(smoothing),
            'warmup': start, 'n_observed': int(n_observed)}


def self_check() -> dict[str, Any]:
    """Check vectorised results against a separate scalar recognition scheduler."""
    rng = np.random.default_rng(2026111109)
    paths = np.array([
        [-.005, .01, -.01, .02, 0., -.02, -.001, .01, -.009, .01, 0., .01, .01, 0., .01],
        [.01, -.003, .02, -.011, -.01, .01, .01, -.003, -.007, 0., .01, .01, .01, .01, .01],
    ])
    original = paths.copy()
    target = rng.uniform(0.0, MAX_TARGET_GAIN, paths.shape)
    pick = rng.random(paths.shape)
    prepared = prepare_ledger_inputs(paths, target_draws=target, pick_draws=pick)
    comparisons = 0
    max_error = 0.0
    for funded in (False, True):
        for probability in (0.0, .5, 1.0):
            for lag in (None, 1, 3, 6):
                actual = transform_paths(prepared, .01, probability, lag,
                                         warmup=3, n_observed=6, return_full=True,
                                         funded_nav=funded)
                for row in range(len(paths)):
                    schedule: dict[int, float] = {}
                    expected = []
                    gap = opening = closing = 0.0
                    for month, raw in enumerate(paths[row]):
                        value = float(np.log1p(raw)) if funded else float(raw)
                        recognised = schedule.pop(month, 0.0)
                        hidden = 0.0
                        if month < 9 and -.01 <= raw < 0 and (probability == 1 or pick[row, month] < probability):
                            desired = float(np.log1p(target[row, month])) if funded else float(target[row, month])
                            hidden = desired - value
                            if lag is not None:
                                schedule[month + lag] = schedule.get(month + lag, 0.0) + hidden
                        gap += hidden - recognised
                        expected.append(value + hidden - recognised)
                        if month == 2:
                            opening = gap
                        if month == 8:
                            closing = gap
                    np.testing.assert_allclose(actual['full_reported_coordinate'][row], expected, atol=1e-16, rtol=1e-13)
                    np.testing.assert_allclose([actual['opening_gap'][row], actual['closing_gap'][row], actual['terminal_gap'][row]],
                                               [opening, closing, gap], atol=1e-16, rtol=1e-13)
                    np.testing.assert_allclose(actual['scheduled_recognitions_after_input'][row].sum(),
                                               0.0 if lag is None else sum(schedule.values()), atol=1e-16)
                    comparisons += 1
                if lag is not None:
                    assert actual['fully_settled'] and actual['settlement_tail_complete']
                max_error = max(max_error, actual['ledger_max_error'])
    assert np.array_equal(paths, original)

    fixed = transform_paths([-.01, 0., .02, 0.], .01, 1., 1,
                            warmup=0, n_observed=2, return_full=True)
    np.testing.assert_allclose(fixed['reported_returns'][0], [.0005, -.0105], atol=1e-16)
    assert fixed['hidden_events'][0] == 1
    partial = transform_paths([.01, 0., .01, -.005], .01, 1., 6,
                              warmup=0, n_observed=4)
    assert partial['reported_returns'][0, -1] > 0
    assert partial['closing_gap'][0] > 0 and not partial['fully_settled']
    np.testing.assert_allclose(partial['scheduled_recognitions_after_window'].sum(axis=1), partial['closing_gap'])
    assert partial['reported_returns'].shape == (1, 4)

    raw_extreme = transform_paths([-1.2, .01, .02], .01, 1., 1, warmup=0, n_observed=2)
    assert raw_extreme['reported_returns'][0, 0] == -1.2
    try:
        transform_funded_nav_paths([-1.2, .01, .02], .01, 1., 1, warmup=0, n_observed=2)
    except ValueError:
        funded_support_rejected = True
    else:
        raise AssertionError('Invalid funded NAV support was accepted')

    for months in (60, 108):
        random_paths = rng.normal(.003, .03, size=(300, 6 + months + 6))
        common = prepare_ledger_inputs(random_paths, rng)
        previous_hidden = None
        for lag in (None, 1, 3, 6):
            audit = transform_paths(common, .02, .5, lag, n_observed=months, return_full=True)
            if previous_hidden is not None:
                assert np.array_equal(previous_hidden, audit['hidden_increments'])
            previous_hidden = audit['hidden_increments']
            if lag is not None:
                assert audit['fully_settled']
            max_error = max(max_error, audit['ledger_max_error'])
        for smoothing in (0., .25, .5, .75, 1.):
            filtered = moving_average_paths(random_paths, smoothing, n_observed=months)
            max_error = max(max_error, filtered['filter_identity_error'])
    return {'scalar_path_policy_comparisons': comparisons,
            'scalar_scheduled_recognition_matches': True,
            'eligibility_uses_underlying_return': True,
            'fixed_target_and_repayment_example': True,
            'opening_closing_and_full_path_identities': True,
            'no_forced_observation_endpoint_settlement': True,
            'scheduled_tail_contains_no_extra_screened_observations': True,
            'raw_spread_support_and_funded_support_are_distinct': funded_support_rejected,
            'inputs_preserved': True, 'paired_draws_across_delays': True,
            'moving_average_endpoint_identity': True,
            'maximum_numerical_identity_error': max_error}


if __name__ == '__main__':
    import json
    print(json.dumps(self_check(), indent=2))
