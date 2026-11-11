"""Observed portfolio descriptions and a fixed, descriptive ridge-logit model."""

from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
import json
import os
import time

for variable in ['OPENBLAS_NUM_THREADS', 'OMP_NUM_THREADS', 'MKL_NUM_THREADS', 'NUMEXPR_NUM_THREADS']:
    os.environ[variable] = '1'

import numpy as np
import pandas as pd
from scipy.optimize import minimize
from scipy.special import expit

from a9_data import ROOT, circular_indices, load_fund_x, load_panel, read_design, read_french
from a9_metrics import raw_scores


FEATURES = ['zero_h', 'skew', 'kurtosis', 'acf1']
RULES = ['conventional_bias', 'conventional_normal', 'conventional_any',
         'legacy_normal_calibrated', 'legacy_bias_calibrated']


def ff3_alpha(dependent, factors, lags=4):
    """Vectorized OLS intercept and Bartlett HAC t-statistic for each column.

    The finite-sample covariance correction is n/(n-4), matching statsmodels
    cov_hac(..., use_correction=True). Only the intercept variance is needed.
    """
    outcomes = np.asarray(dependent, dtype=float)
    regressors = np.column_stack([np.ones(len(factors)), np.asarray(factors, dtype=float)])
    if outcomes.ndim == 1:
        outcomes = outcomes[:, None]
    if not np.isfinite(outcomes).all() or not np.isfinite(regressors).all():
        raise ValueError('FF3 regressions require complete finite histories')
    if outcomes.shape[0] != regressors.shape[0] or np.linalg.matrix_rank(regressors) != 4:
        raise ValueError('FF3 regression dimensions or rank are invalid')
    observations, parameters = regressors.shape
    inverse = np.linalg.inv(regressors.T @ regressors)
    coefficients = inverse @ regressors.T @ outcomes
    residuals = outcomes - regressors @ coefficients
    intercept_influence = residuals * (regressors @ inverse[:, 0])[:, None]
    variance = np.sum(intercept_influence ** 2, axis=0)
    for lag in range(1, min(lags, observations - 1) + 1):
        bartlett_weight = 1 - lag / (lags + 1)
        variance += 2 * bartlett_weight * np.sum(
            intercept_influence[lag:] * intercept_influence[:-lag], axis=0)
    variance *= observations / (observations - parameters)
    if np.any(variance <= 0):
        raise ArithmeticError('Nonpositive FF3 intercept variance')
    return coefficients[0], coefficients[0] / np.sqrt(variance)


def flags_from_scores(scores):
    bias = scores['B'] > 2
    normal = scores['normal_p'] < 0.05
    return {
        'conventional_bias': bias,
        'conventional_normal': normal,
        'conventional_any': bias | normal,
        'legacy_normal_calibrated': scores['normal_p'] < 0.21,
        'legacy_bias_calibrated': scores['B'] > 3.36,
    }


def describe_cohort(frame, risk_free, ff3, weighting, representation, documentation):
    spreads = frame.to_numpy(dtype=float)
    cash = risk_free.to_numpy(dtype=float)
    observed = spreads if representation == 'spread' else spreads + cash[:, None]
    if not np.isfinite(observed).all():
        raise ValueError('The descriptive cohort contains missing observations')
    scores = raw_scores(observed.T)
    alphas, alpha_t = ff3_alpha(spreads, ff3)
    excess_sharpe = spreads.mean(axis=0) / spreads.std(axis=0, ddof=1)
    result = pd.DataFrame({
        'signal': frame.columns,
        'weighting': weighting,
        'representation': representation,
        'cohort': 'all195_complete_common',
        'start': str(frame.index[0]),
        'end': str(frame.index[-1]),
        'months': len(frame),
        'excess_sharpe': excess_sharpe,
        'zero_h': scores['sharpe'],
        'ff3_alpha': alphas,
        'ff3_alpha_t_hac4': alpha_t,
    })
    for field in ['mean', 'sd', 'skew', 'kurtosis', 'acf1', 'B', 'D', 'normal_p', 'negative']:
        result[field] = scores[field]
    for method, flag in flags_from_scores(scores).items():
        result[method] = flag
    result['publication_year'] = documentation.loc[frame.columns, 'Year'].to_numpy()
    result['source_original_weight'] = documentation.loc[frame.columns, 'Stock Weight'].to_numpy()
    result['source_sample_end_year'] = documentation.loc[frame.columns, 'SampleEndYear'].to_numpy()
    result['signal_description'] = documentation.loc[frame.columns, 'LongDescription'].to_numpy()
    result['return_basis'] = ('published zero-investment LS payoff' if representation == 'spread'
                              else 'RF plus one unit of LS payoff per unit of collateral')
    return result, observed


def describe_fund_x(series, french, label):
    factors = french.reindex(series.index)
    if not np.isfinite(factors.to_numpy()).all():
        raise ValueError('Fund X reference contains missing French factor observations')
    observed = series.to_numpy(dtype=float)
    excess = observed - factors['RF'].to_numpy()
    scores = raw_scores(observed[None, :])
    alphas, alpha_t = ff3_alpha(excess, factors[['Mkt-RF', 'SMB', 'HML']])
    result = dict(signal='Fund X', weighting='fund_x', representation='reported_total_return',
                  cohort=label, start=str(series.index[0]), end=str(series.index[-1]), months=len(series),
                  excess_sharpe=float(excess.mean() / excess.std(ddof=1)),
                  zero_h=float(scores['sharpe'][0]), ff3_alpha=float(alphas[0]),
                  ff3_alpha_t_hac4=float(alpha_t[0]),
                  publication_year=None, source_original_weight=None, source_sample_end_year=None,
                  signal_description='Frozen published Fund X I-series net USD returns',
                  return_basis='reported investor total return net of fees')
    for field in ['mean', 'sd', 'skew', 'kurtosis', 'acf1', 'B', 'D', 'normal_p', 'negative']:
        result[field] = scores[field][0]
    for method, flag in flags_from_scores(scores).items():
        result[method] = bool(flag[0])
    return result


def ridge_logit(features, flags):
    """Fit a descriptive standardized model with the prespecified penalties."""
    covariates = np.asarray(features, dtype=float)
    outcomes = np.asarray(flags, dtype=float)
    feature_mean = covariates.mean(axis=0)
    feature_sd = covariates.std(axis=0, ddof=1)
    safe_sd = np.where(feature_sd > 0, feature_sd, 1.0)
    standardized = (covariates - feature_mean) / safe_sd
    design = np.column_stack([np.ones(len(outcomes)), standardized])
    penalties = np.array([1e-6, 0.01, 0.01, 0.01, 0.01])

    def objective(coefficients):
        linear = design @ coefficients
        value = np.mean(np.logaddexp(0, linear) - outcomes * linear)
        value += 0.5 * np.sum(penalties * coefficients ** 2)
        gradient = design.T @ (expit(linear) - outcomes) / len(outcomes)
        gradient += penalties * coefficients
        return value, gradient

    initial = np.zeros(5)
    initial_rate = np.clip(outcomes.mean(), 1e-6, 1 - 1e-6)
    initial[0] = np.log(initial_rate / (1 - initial_rate))
    fit = minimize(objective, initial, jac=True, method='L-BFGS-B',
                   options={'maxiter': 1000, 'gtol': 1e-9, 'ftol': 1e-13})
    gradient_max = float(np.max(np.abs(fit.jac)))
    if not fit.success or gradient_max > 2e-6 or not np.isfinite(fit.x).all():
        raise ArithmeticError(f'Ridge logit failed: success={fit.success}, gradient={gradient_max}')
    return dict(coefficients=fit.x, feature_mean=feature_mean, feature_sd=feature_sd,
                objective=float(fit.fun), gradient_max=gradient_max)


def regression_features(scores):
    return np.column_stack([scores['sharpe'], scores['skew'], scores['kurtosis'], scores['acf1']])


def logit_with_calendar_bootstrap(observed, indices):
    point_scores = raw_scores(observed.T)
    point_flags = flags_from_scores(point_scores)['conventional_any']
    point = ridge_logit(regression_features(point_scores), point_flags)
    coefficients = np.empty((len(indices), 5))
    largest_gradient = point['gradient_max']
    for replicate, months in enumerate(indices):
        scores = raw_scores(observed[months].T)
        flags = flags_from_scores(scores)['conventional_any']
        fitted = ridge_logit(regression_features(scores), flags)
        coefficients[replicate] = fitted['coefficients']
        largest_gradient = max(largest_gradient, fitted['gradient_max'])
    bounds = np.quantile(coefficients, [0.025, 0.975], axis=0)
    rows = []
    for term_index, term in enumerate(['intercept'] + FEATURES):
        rows.append(dict(term=term, coefficient=float(point['coefficients'][term_index]),
                         lo=float(bounds[0, term_index]), hi=float(bounds[1, term_index]),
                         feature_mean=None if term_index == 0 else float(point['feature_mean'][term_index - 1]),
                         feature_sd=None if term_index == 0 else float(point['feature_sd'][term_index - 1]),
                         point_flag_rate=float(point_flags.mean()), objective=point['objective'],
                         bootstrap_draws=len(indices), block_months=12,
                         max_gradient_all_fits=largest_gradient))
    return rows


def independent_checks(frame, factors):
    """Check the vectorized HAC calculation against a separate implementation."""
    import statsmodels.api as sm
    from statsmodels.stats.sandwich_covariance import cov_hac

    candidates = frame.iloc[:, [0, len(frame.columns) // 2, -1]].to_numpy()
    alphas, t_values = ff3_alpha(candidates, factors)
    regressors = sm.add_constant(factors.to_numpy(), has_constant='add')
    for index in range(candidates.shape[1]):
        fit = sm.OLS(candidates[:, index], regressors).fit()
        covariance = cov_hac(fit, nlags=4, use_correction=True)
        assert np.isclose(alphas[index], fit.params[0], atol=1e-12, rtol=1e-11)
        assert np.isclose(t_values[index], fit.params[0] / np.sqrt(covariance[0, 0]),
                          atol=1e-11, rtol=1e-10)
    # The fixed penalty keeps estimates finite even for a separated outcome.
    covariates = np.column_stack([np.linspace(-2, 2, 20), np.zeros((20, 3))])
    separated = np.r_[np.zeros(10), np.ones(10)]
    fitted = ridge_logit(covariates, separated)
    assert np.isfinite(fitted['coefficients']).all()
    assert fitted['coefficients'][1] > 0
    return dict(hac4_matches_statsmodels_cases=3, separated_logit_finite=True)


def main():
    started = time.monotonic()
    design = read_design()
    source_doc = pd.read_csv(ROOT / 'data/raw/SignalDoc.csv').set_index('Acronym', verify_integrity=True)
    french = read_french()
    start = design['descriptive_start']
    end = design['latest_common_month']
    common_months = pd.period_range(start, end, freq='M')
    factors = french.reindex(common_months)
    if not np.isfinite(factors.to_numpy()).all():
        raise ValueError('Missing common French factors')

    tables = ROOT / 'tables'
    tables.mkdir(exist_ok=True)
    panels = {weighting: load_panel(weighting, descriptive=True).loc[start:end]
              for weighting in ['original', 'value_weighted']}
    for frame in panels.values():
        if frame.shape != (108, 195) or not frame.index.equals(common_months):
            raise ValueError('Unexpected fixed descriptive cohort')
        if not np.isfinite(frame.to_numpy()).all():
            raise ValueError('Missing observations in the fixed descriptive cohort')
    assert panels['original'].columns.equals(panels['value_weighted'].columns)
    checks = independent_checks(panels['original'], factors[['Mkt-RF', 'SMB', 'HML']])

    seed_sequence = [design['seed'], 9, 30]
    rng = np.random.default_rng(np.random.SeedSequence(seed_sequence))
    indices = circular_indices(rng, histories=300, length=108, source_length=108, block=12)
    descriptions = []
    logit_rows = []
    for weighting, frame in panels.items():
        for representation in ['spread', 'funded']:
            description, observed = describe_cohort(
                frame, factors['RF'], factors[['Mkt-RF', 'SMB', 'HML']],
                weighting, representation, source_doc)
            descriptions.append(description)
            coefficients = logit_with_calendar_bootstrap(observed, indices)
            for row in coefficients:
                row.update(weighting=weighting, representation=representation,
                           cohort='all195_complete_common', months=108,
                           start=start, end=end, n_strategies=195)
            logit_rows.extend(coefficients)
            print(json.dumps(dict(stage='descriptive_complete', weighting=weighting,
                                  representation=representation,
                                  conventional_any_count=int(description['conventional_any'].sum()))), flush=True)

    primary = descriptions[0]
    order = primary.sort_values(['excess_sharpe', 'signal'], kind='stable').index
    primary['sharpe_quintile'] = 0
    primary.loc[order, 'sharpe_quintile'] = np.repeat(np.arange(1, 6), 39)
    quintile_rows = []
    for quintile, group in primary.groupby('sharpe_quintile', sort=True):
        assert len(group) == 39
        for method in RULES:
            quintile_rows.append(dict(weighting='original', representation='spread', months=108,
                                      start=start, end=end, quintile=int(quintile), method=method,
                                      n_strategies=len(group), alert_count=int(group[method].sum()),
                                      rate=float(group[method].mean()),
                                      min_excess_sharpe=float(group['excess_sharpe'].min()),
                                      max_excess_sharpe=float(group['excess_sharpe'].max()),
                                      mean_excess_sharpe=float(group['excess_sharpe'].mean()),
                                      mean_skew=float(group['skew'].mean()),
                                      mean_kurtosis=float(group['kurtosis'].mean()),
                                      mean_acf1=float(group['acf1'].mean())))

    fund = load_fund_x()
    fund_rows = [describe_fund_x(fund, french, 'fund_x_full117'),
                 describe_fund_x(fund.loc[start:end], french, 'fund_x_common108')]
    complete = pd.concat(descriptions + [pd.DataFrame(fund_rows)], ignore_index=True)
    complete.to_csv(tables / 'descriptive_statistics.csv', index=False)
    pd.DataFrame(quintile_rows).to_csv(tables / 'descriptive_quintiles.csv', index=False)
    pd.DataFrame(logit_rows).to_csv(tables / 'descriptive_logit.csv', index=False)

    maximum = primary.loc[primary['zero_h'].idxmax()]
    common_fund = fund_rows[1]
    metadata = dict(
        completed_utc=datetime.now(timezone.utc).isoformat(),
        descriptive_signals=195, common_months=108, descriptive_rows=len(complete),
        return_units='decimal',
        performance_sharpe='LS mean/sample SD; funded excess over RF equals LS; Fund X uses its return minus RF',
        zero_h='mean of the actual diagnostic series divided by its sample SD',
        factor_regression='FF3 US; dependent LS directly, funded minus RF=LS, Fund X minus RF',
        hac=dict(lags=4, kernel='Bartlett', finite_sample_correction='n/(n-4)'),
        primary_quintiles='Original spread series sorted by common-history excess Sharpe, Q1 low/Q5 high,39 each; alphabetical exact tie break',
        quintile_intervals='Point frequencies only; strategies share stocks and calendar observations',
        ridge_logit=dict(outcome='either conventional screen', features=FEATURES,
                         standardization='Cross-strategy mean and sample SD recomputed in each fit',
                         objective='mean Bernoulli negative log likelihood +0.01*sum(slope^2)/2+1e-6*intercept^2/2',
                         uncertainty='Joint circular calendar-block bootstrap; same calendar indices for all195 strategies, representations, weightings and RF',
                         seed_sequence=seed_sequence, draws=300, block_months=12,
                         interpretation='Descriptive same-history association, not a causal or independent cross-sectional model',
                         percentile_range='Conditional calendar-block refit range; rare threshold events can put the point estimate outside the percentile range',
                         cohort_event_counts=[dict(weighting=frame['weighting'].iloc[0],
                                                   representation=frame['representation'].iloc[0],
                                                   events=int(frame['conventional_any'].sum()),
                                                   strategies=len(frame)) for frame in descriptions]),
        independent_checks=checks,
        primary_highest_h=dict(signal=maximum['signal'], h=float(maximum['zero_h'])),
        fund_x_common_h=float(common_fund['zero_h']),
        primary_series_reaching_fund_x_h=int((primary['zero_h'] >= common_fund['zero_h']).sum()),
        elapsed_seconds=time.monotonic() - started,
        code_sha256=sha256(Path(__file__).read_bytes()).hexdigest(),
        design_sha256=sha256((ROOT / 'data/frozen_design.json').read_bytes()).hexdigest(),
    )
    (ROOT / 'data/descriptive_metadata.json').write_text(json.dumps(metadata, indent=2) + '\n')
    print(json.dumps(metadata, indent=2))


if __name__ == '__main__':
    main()
