"""Monthly payoff diagnostics and exact selection weights for Assignment 9.

Rows are complete return histories and columns are months. Returns/payoffs are
decimals. Missing values and constant histories are rejected, never imputed.
The mean/standard-deviation ratio uses a zero reference rate. The caller chooses
the economic payoff convention before using these diagnostics.
"""

from itertools import combinations
from math import comb, erfc, sqrt
from numbers import Integral

import numpy as np
from scipy.stats import binom, kurtosis, norm, skew


def raw_scores(returns):
    """Return vectorized diagnostics using the established A8 conventions.

    The bias ratio includes zero in the upper band [0, sample SD] and excludes
    it from the lower band [-sample SD, 0). The normal-count p-value is a fitted
    binomial diagnostic. It treats its estimated loss probability as fixed.

    Skewness is the adjusted Fisher-Pearson sample coefficient. Excess kurtosis
    uses the unbiased Fisher convention. ACF1 is the lag-one centered product
    sum divided by the full-sample centered sum of squares, matching A3 and the
    default unadjusted sample ACF convention.
    """
    values = np.asarray(returns, dtype=np.float64)
    if values.ndim != 2 or values.shape[0] == 0 or values.shape[1] < 4:
        raise ValueError('Expected one or more complete histories of at least four months')
    if not np.isfinite(values).all():
        raise ValueError('Return histories must contain only finite observations')

    months = values.shape[1]
    means = values.mean(axis=1)
    standard_deviations = values.std(axis=1, ddof=1)
    if np.any(standard_deviations <= 0) or not np.isfinite(standard_deviations).all():
        raise ValueError('Every history must have finite positive sample variance')
    centered = values - means[:, None]
    sum_squares = np.sum(centered * centered, axis=1)
    sharpes = means / standard_deviations

    negative_counts = np.sum(values < 0, axis=1)
    upper_counts = np.sum((values >= 0) & (values <= standard_deviations[:, None]), axis=1)
    lower_counts = np.sum((values >= -standard_deviations[:, None]) & (values < 0), axis=1)
    fitted_loss_probabilities = norm.cdf(-sharpes)
    sample_excess_kurtosis = kurtosis(values, axis=1, fisher=True, bias=False)
    return {
        'B': upper_counts / (1.0 + lower_counts),
        'D': months * fitted_loss_probabilities - negative_counts,
        'sharpe': sharpes,
        'normal_p': binom.cdf(negative_counts, months, fitted_loss_probabilities),
        'negative': negative_counts,
        'upper_count': upper_counts,
        'lower_count': lower_counts,
        'mean': means,
        'sd': standard_deviations,
        'skew': skew(values, axis=1, bias=False),
        'kurtosis': sample_excess_kurtosis,
        'excess_kurtosis': sample_excess_kurtosis,
        'acf1': np.sum(centered[:, 1:] * centered[:, :-1], axis=1) / sum_squares,
    }


def fit_score_maps(bias_scores, deficit_scores):
    """Freeze sorted development scores for the two marginal rank maps."""
    bias = np.asarray(bias_scores, dtype=np.float64)
    deficit = np.asarray(deficit_scores, dtype=np.float64)
    if bias.ndim != 1 or bias.size == 0 or deficit.shape != bias.shape:
        raise ValueError('Development scores must be nonempty matching one-dimensional arrays')
    if not np.isfinite(bias).all() or not np.isfinite(deficit).all():
        raise ValueError('Development scores must be finite')
    return np.sort(bias), np.sort(deficit)


def combined_scores(bias_scores, deficit_scores, maps):
    """Maximum of the frozen right-inclusive marginal development ranks.

    Each rank is count(development score <= observed score)/(development N+1),
    as in A8. These are fixed score transformations, rather than p-values.
    Equal scores receive equal ranks, including ties at the calibration cutoff.
    """
    bias = np.asarray(bias_scores, dtype=np.float64)
    deficit = np.asarray(deficit_scores, dtype=np.float64)
    if bias.shape != deficit.shape or not np.isfinite(bias).all() or not np.isfinite(deficit).all():
        raise ValueError('Evaluation scores must have matching shapes and finite values')
    if len(maps) != 2:
        raise ValueError('Expected the two frozen marginal score maps')
    sorted_bias = np.asarray(maps[0], dtype=np.float64)
    sorted_deficit = np.asarray(maps[1], dtype=np.float64)
    for reference in (sorted_bias, sorted_deficit):
        if reference.ndim != 1 or reference.size == 0 or not np.isfinite(reference).all():
            raise ValueError('Each score map must be a nonempty finite sorted array')
        if np.any(reference[1:] < reference[:-1]):
            raise ValueError('Score maps must be sorted in ascending order')
    bias_rank = np.searchsorted(sorted_bias, bias, side='right') / (sorted_bias.size + 1.0)
    deficit_rank = np.searchsorted(sorted_deficit, deficit, side='right') / (sorted_deficit.size + 1.0)
    return np.maximum(bias_rank, deficit_rank)


def winner_weights(population_size, subset_size):
    """Winner probabilities for ordinal ranks 1,...,N, best first.

    A uniform subset of K distinct members is selected without replacement.
    Rank j wins exactly when it is included along with K-1 worse ranks, giving
    C(N-j, K-1)/C(N, K). The recurrence avoids large factorials. This is a finite
    population identity conditional on the observed ranking and makes no
    independence assumption about the strategies' return histories.
    """
    if isinstance(population_size, bool) or not isinstance(population_size, Integral):
        raise ValueError('Population size must be a positive integer')
    if isinstance(subset_size, bool) or not isinstance(subset_size, Integral):
        raise ValueError('Subset size must be an integer between one and population size')
    population_size = int(population_size)
    subset_size = int(subset_size)
    if population_size < 1 or not 1 <= subset_size <= population_size:
        raise ValueError('Require 1 <= subset size <= population size')

    probabilities = np.zeros(population_size, dtype=np.float64)
    probabilities[0] = subset_size / population_size
    for rank in range(1, population_size - subset_size + 1):
        probabilities[rank] = (
            probabilities[rank - 1]
            * (population_size - rank - subset_size + 1)
            / (population_size - rank)
        )
    # Correct only accumulated floating-point error, retaining the exact support.
    probabilities /= probabilities.sum()
    return probabilities


def finite_population_winner_weights(sharpes, subset_size):
    """Return winner probabilities aligned with the input strategy order.

    Ranking uses descending Sharpe. Exact Sharpe ties use input order as a
    deterministic tie-break, so callers should fix that order before outcomes.
    """
    values = np.asarray(sharpes, dtype=np.float64)
    if values.ndim != 1 or values.size == 0 or not np.isfinite(values).all():
        raise ValueError('Sharpes must be a nonempty finite one-dimensional array')
    rank_probabilities = winner_weights(values.size, subset_size)
    order = np.argsort(-values, kind='stable')
    probabilities = np.empty(values.size, dtype=np.float64)
    probabilities[order] = rank_probabilities
    return probabilities


def weighted_quantile(values, weights=None, quantile=0.95):
    """Return the first observed score whose cumulative weight reaches q.

    There is no interpolation. Zero-weight observations are excluded. When the
    screening rule is strictly score > cutoff, the weighted calibration mass
    above the returned cutoff is at most 1-q, including arbitrary score ties.
    """
    scores = np.asarray(values, dtype=np.float64)
    if scores.ndim != 1 or scores.size == 0 or not np.isfinite(scores).all():
        raise ValueError('Scores must be a nonempty finite one-dimensional array')
    if not np.isfinite(quantile) or not 0 <= quantile <= 1:
        raise ValueError('Quantile probability must lie in [0, 1]')
    masses = np.ones(scores.size, dtype=np.float64) if weights is None else np.asarray(weights, dtype=np.float64)
    if masses.shape != scores.shape or not np.isfinite(masses).all() or np.any(masses < 0):
        raise ValueError('Weights must be matching finite nonnegative masses')
    positive = masses > 0
    if not positive.any():
        raise ValueError('At least one calibration weight must be positive')
    scores = scores[positive]
    masses = masses[positive]
    order = np.argsort(scores, kind='stable')
    scores = scores[order]
    masses = masses[order]
    # Scaling first avoids overflow when valid input weights are very large.
    masses = masses / masses.max()
    cumulative_mass = np.cumsum(masses)
    target_mass = quantile * cumulative_mass[-1]
    index = int(np.searchsorted(cumulative_mass, target_mass, side='left'))
    return float(scores[min(index, scores.size - 1)])


def self_check():
    """Scalar score references, exhaustive small subsets and tied cutoffs."""
    sample = np.array([
        [-0.03, 0.0, 0.004, 0.01, 0.02, -0.005, 0.07, 0.015],
        [0.01, 0.015, 0.02, -0.002, 0.0, 0.004, 0.05, -0.006],
    ])
    computed = raw_scores(sample)
    for index, row in enumerate(sample):
        months = len(row)
        mean_return = sum(float(value) for value in row) / months
        centered = [float(value) - mean_return for value in row]
        sum_squares = sum(value * value for value in centered)
        sample_sd = sqrt(sum_squares / (months - 1))
        monthly_sharpe = mean_return / sample_sd
        loss_probability = 0.5 * erfc(monthly_sharpe / sqrt(2.0))
        losses = sum(value < 0 for value in row)
        upper = sum(0 <= value <= sample_sd for value in row)
        lower = sum(-sample_sd <= value < 0 for value in row)
        normal_p = sum(
            comb(months, count) * loss_probability ** count
            * (1 - loss_probability) ** (months - count)
            for count in range(losses + 1)
        )
        expected = {
            'B': upper / (1 + lower), 'D': months * loss_probability - losses,
            'normal_p': normal_p, 'mean': mean_return, 'sd': sample_sd,
            'sharpe': monthly_sharpe, 'negative': losses,
            'acf1': sum(centered[t] * centered[t - 1] for t in range(1, months)) / sum_squares,
        }
        population_sd = sqrt(sum_squares / months)
        third_moment = sum((value / population_sd) ** 3 for value in centered) / months
        fourth_excess = sum((value / population_sd) ** 4 for value in centered) / months - 3
        expected['skew'] = sqrt(months * (months - 1)) / (months - 2) * third_moment
        expected['excess_kurtosis'] = (
            (months - 1) / ((months - 2) * (months - 3))
            * ((months + 1) * fourth_excess + 6)
        )
        for name, value in expected.items():
            assert np.isclose(computed[name][index], value, atol=1e-12, rtol=1e-12), name

    zeros = raw_scores(np.array([[-1.0, 0.0, 0.0, 1.0]]))
    assert zeros['upper_count'][0] == 2 and zeros['lower_count'][0] == 0
    endpoints = raw_scores(np.array([[-sqrt(2), -1.0, 1.0, sqrt(2)]]))
    assert endpoints['upper_count'][0] == 2 and endpoints['lower_count'][0] == 2
    for name in ['B', 'D', 'normal_p', 'sharpe', 'skew', 'excess_kurtosis', 'acf1']:
        assert np.allclose(raw_scores(sample * 3.0)[name], computed[name], atol=1e-12, rtol=1e-12), name

    subset_cases = 0
    for population_size in range(1, 10):
        for subset_size in range(1, population_size + 1):
            counts = np.zeros(population_size)
            for members in combinations(range(population_size), subset_size):
                counts[min(members)] += 1
            enumeration = counts / comb(population_size, subset_size)
            assert np.allclose(winner_weights(population_size, subset_size), enumeration, atol=1e-14)
            direct = np.array([
                comb(population_size - rank, subset_size - 1) / comb(population_size, subset_size)
                if population_size - rank >= subset_size - 1 else 0.0
                for rank in range(1, population_size + 1)
            ])
            assert np.allclose(winner_weights(population_size, subset_size), direct, atol=1e-14)
            subset_cases += 1
    sharpes = np.array([0.2, 0.5, 0.5, 0.1])
    aligned = finite_population_winner_weights(sharpes, 2)
    enumerated = np.zeros(sharpes.size)
    for members in combinations(range(sharpes.size), 2):
        winner = min(members, key=lambda member: (-sharpes[member], member))
        enumerated[winner] += 1 / comb(sharpes.size, 2)
    assert np.allclose(aligned, enumerated)
    large_subset_cases = 0
    for subset_size in [1, 5, 20, 50, 100, 212]:
        probabilities = winner_weights(212, subset_size)
        assert np.isclose(probabilities.sum(), 1.0, atol=1e-14)
        assert np.all(probabilities >= 0)
        assert np.all(probabilities[1:] <= probabilities[:-1])
        large_subset_cases += 1

    values = np.array([0.0, 1.0, 1.0, 2.0, 3.0])
    weights = np.array([0.0, 0.2, 0.4, 0.3, 0.1])
    for probability in [0, 0.25, 0.6, 0.9, 0.95, 1]:
        cutoff = weighted_quantile(values, weights, quantile=probability)
        tail_mass = weights[values > cutoff].sum() / weights.sum()
        assert tail_mass <= 1 - probability + 1e-14
    maps = fit_score_maps(np.array([1.0, 1.0, 2.0]), np.array([-1.0, 0.0, 0.0]))
    combined = combined_scores(np.array([1.0, 0.0, 2.0]), np.array([0.0, -1.0, 0.0]), maps)
    assert np.allclose(combined, [0.75, 0.25, 0.75])
    return {
        'scalar_metrics_match': True,
        'zero_and_band_endpoints_match': True,
        'positive_scale_invariance': True,
        'exhaustive_subset_cases': subset_cases,
        'requested_size_stability_cases': large_subset_cases,
        'deterministic_sharpe_ties_match': True,
        'weighted_strict_tail_with_ties': True,
        'fixed_cdf_maps_match': True,
    }


if __name__ == '__main__':
    import json
    print(json.dumps(self_check(), indent=2))
