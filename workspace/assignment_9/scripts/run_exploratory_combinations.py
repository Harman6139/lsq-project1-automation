"""Fixed calibration-period combinations, evaluated on later observed months."""

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

from a9_data import ROOT, load_fund_x, load_panel, read_design, read_french
from a9_metrics import raw_scores


OPTIMIZER = dict(method='SLSQP', starting_weights='uniform', ftol=1e-10,
                 maxiter=2000, weight_lower_bound=0.0, weight_cap=0.05,
                 covariance_sample_fraction=0.5, covariance_diagonal_fraction=0.5,
                 retries=0)
RULES = ['equal_notional', 'inverse_calibration_volatility', 'maximum_calibration_sharpe']


def calibration_objective(weights, means, covariance):
    """Negative calibration Sharpe and its analytic weight gradient."""
    covariance_weight = covariance @ weights
    variance = float(weights @ covariance_weight)
    if variance <= 0:
        raise ArithmeticError('Combination calibration variance must be positive')
    volatility = np.sqrt(variance)
    mean = float(weights @ means)
    value = -mean / volatility
    gradient = -means / volatility + mean * covariance_weight / volatility ** 3
    return value, gradient


def estimate_weights(calibration):
    values = calibration.to_numpy(dtype=float)
    strategies = values.shape[1]
    means = values.mean(axis=0)
    standard_deviations = values.std(axis=0, ddof=1)
    if np.any(standard_deviations <= 0):
        raise ValueError('Inverse-volatility weights require positive calibration SDs')
    sample_covariance = np.cov(values, rowvar=False, ddof=1)
    covariance = 0.5 * sample_covariance + 0.5 * np.diag(np.diag(sample_covariance))
    uniform = np.full(strategies, 1 / strategies)
    inverse_sd = 1 / standard_deviations
    inverse_sd /= inverse_sd.sum()

    # Check the objective gradient independently along one feasible direction.
    direction = np.cos(np.arange(strategies, dtype=float))
    direction -= direction.mean()
    direction /= np.max(np.abs(direction))
    step = 1e-6
    above = calibration_objective(uniform + step * direction, means, covariance)[0]
    below = calibration_objective(uniform - step * direction, means, covariance)[0]
    analytic = float(calibration_objective(uniform, means, covariance)[1] @ direction)
    numerical = (above - below) / (2 * step)
    if not np.isclose(analytic, numerical, atol=2e-7, rtol=2e-6):
        raise ArithmeticError('Calibration objective gradient check failed')

    fit = minimize(
        calibration_objective, uniform, args=(means, covariance), jac=True,
        method=OPTIMIZER['method'], bounds=[(0.0, 0.05)] * strategies,
        constraints={'type': 'eq', 'fun': lambda weights: weights.sum() - 1,
                     'jac': lambda weights: np.ones_like(weights)},
        options={'ftol': OPTIMIZER['ftol'], 'maxiter': OPTIMIZER['maxiter'], 'disp': False},
    )
    information = dict(success=bool(fit.success), status=int(fit.status),
                       message=str(fit.message), iterations=int(fit.nit),
                       objective=float(fit.fun), regularized_calibration_sharpe=float(-fit.fun),
                       sum_weights=float(fit.x.sum()), min_weight=float(fit.x.min()),
                       max_weight=float(fit.x.max()),
                       gradient_directional_absolute_error=float(abs(analytic - numerical)))
    if not fit.success:
        return None, information
    if abs(fit.x.sum() - 1) > 1e-7 or fit.x.min() < -1e-8 or fit.x.max() > 0.05 + 1e-8:
        raise ArithmeticError('Constrained optimizer returned infeasible weights')
    weights = dict(zip(RULES, [uniform, inverse_sd, fit.x]))
    for vector in weights.values():
        assert np.isfinite(vector).all() and abs(vector.sum() - 1) < 1e-7
        assert vector.min() >= -1e-8
    return weights, information


def metric_record(values, spread, weighting, rule, representation, index):
    scores = raw_scores(values[None, :])
    record = dict(weighting=weighting, rule=rule, representation=representation,
                  start=str(index[0]), end=str(index[-1]), months=len(index),
                  excess_sharpe=float(spread.mean() / spread.std(ddof=1)),
                  zero_h=float(scores['sharpe'][0]),
                  conventional_bias=bool(scores['B'][0] > 2),
                  conventional_normal=bool(scores['normal_p'][0] < 0.05),
                  conventional_any=bool((scores['B'][0] > 2) or (scores['normal_p'][0] < 0.05)),
                  costs='source gross of trading, borrowing and management costs')
    for field in ['mean', 'sd', 'skew', 'kurtosis', 'acf1', 'B', 'D', 'normal_p', 'negative']:
        record[field] = float(scores[field][0])
    return record


def main():
    started = time.monotonic()
    config_path = ROOT / 'data/exploratory_combination_design.json'
    config_bytes = config_path.read_bytes()
    configuration = json.loads(config_bytes)
    design = read_design()
    expected_rules = [
        'equal notional', 'inverse calibration volatility',
        'maximum calibration Sharpe with long-only factor weights summingto1, cap.05 and covariance .5*sample+.5*diagonal',
    ]
    if configuration['rules'] != expected_rules:
        raise ValueError('Unexpected exploratory rule specification')
    calibration_start, calibration_end = configuration['weight_estimation']
    evaluation_start, evaluation_end = configuration['evaluation']
    metadata = dict(
        status='running', started_utc=datetime.now(timezone.utc).isoformat(),
        exploratory_status=configuration['status'], configuration=configuration,
        optimizer_settings=OPTIMIZER, config_sha256=sha256(config_bytes).hexdigest(),
        source_sha256={}, optimizer_results={},
    )
    dependencies = [
        ROOT / 'data/frozen_design.json', ROOT / 'data/source_provenance.json',
        ROOT / 'data/raw/PredictorLSretWide.parquet', ROOT / 'data/raw/PredictorVWforce.parquet',
        ROOT / 'data/raw/SignalDoc.csv', ROOT / 'data/raw/F-F_Research_Data_Factors.csv',
        ROOT / 'data/raw/fund_x_2017_01_to_2026_09.csv',
        ROOT / 'scripts/a9_data.py', ROOT / 'scripts/a9_metrics.py', Path(__file__),
    ]
    for path in dependencies:
        metadata['source_sha256'][path.relative_to(ROOT).as_posix()] = sha256(path.read_bytes()).hexdigest()
    metadata_path = ROOT / 'data/exploratory_combination_metadata.json'
    metadata_path.write_text(json.dumps(metadata, indent=2) + '\n')

    documentation = pd.read_csv(ROOT / 'data/raw/SignalDoc.csv').set_index('Acronym', verify_integrity=True)
    core_signals = design['core_signals']
    if len(core_signals) != 194 or (documentation.loc[core_signals, 'Year'] > 2016).any():
        raise ValueError('Unexpected core strategy count or publication dates')
    french = read_french()
    evaluation_index = pd.period_range(evaluation_start, evaluation_end, freq='M')
    cash = french.reindex(evaluation_index)['RF'].to_numpy()
    if not np.isfinite(cash).all():
        raise ValueError('Missing evaluation risk-free returns')
    fund = load_fund_x().reindex(evaluation_index)
    if fund.isna().any():
        raise ValueError('Missing common-period Fund X return')
    fund_score = raw_scores(fund.to_numpy()[None, :])
    metadata['fund_x_common_zero_h'] = float(fund_score['sharpe'][0])
    metadata['fund_x_common_excess_sharpe'] = float((fund.to_numpy() - cash).mean()
                                                       / (fund.to_numpy() - cash).std(ddof=1))

    weight_rows = []
    monthly_rows = []
    statistics_rows = []
    for weighting in ['original', 'value_weighted']:
        panel = load_panel(weighting)
        if list(panel.columns) != core_signals:
            raise ValueError('Both weightings must use the same ordered194 core strategies')
        calibration = panel.loc[calibration_start:calibration_end]
        evaluation = panel.reindex(evaluation_index)
        if calibration.shape != (144, 194) or evaluation.shape != (108, 194):
            raise ValueError('Unexpected calibration or evaluation dimensions')
        if not np.isfinite(calibration.to_numpy()).all() or not np.isfinite(evaluation.to_numpy()).all():
            raise ValueError('Missing strategy observations; imputation is forbidden')
        weights, fit_information = estimate_weights(calibration)
        metadata['optimizer_results'][weighting] = fit_information
        metadata_path.write_text(json.dumps(metadata, indent=2) + '\n')
        if weights is None:
            metadata['status'] = 'optimizer_failed_without_model_retry'
            metadata_path.write_text(json.dumps(metadata, indent=2) + '\n')
            raise RuntimeError(f'Prespecified maximum-Sharpe optimizer failed for {weighting}')

        for rule, vector in weights.items():
            calibration_returns = calibration.to_numpy() @ vector
            spread = evaluation.to_numpy() @ vector
            funded = cash + spread
            for month_index in [0, len(evaluation) - 1]:
                scalar = sum(float(evaluation.iloc[month_index, i]) * float(vector[i])
                             for i in range(len(vector)))
                assert np.isclose(spread[month_index], scalar, atol=1e-14, rtol=1e-13)
            assert np.allclose(funded - spread, cash, atol=1e-14, rtol=1e-13)
            for signal, weight in zip(core_signals, vector):
                weight_rows.append(dict(weighting=weighting, rule=rule, signal=signal,
                                        weight=float(weight), calibration_start=calibration_start,
                                        calibration_end=calibration_end,
                                        publication_year=int(documentation.loc[signal, 'Year']),
                                        source_original_weight=documentation.loc[signal, 'Stock Weight']))
            for month, ls_return, rf_return, funded_return in zip(evaluation_index, spread, cash, funded):
                monthly_rows.append(dict(weighting=weighting, rule=rule, month=str(month),
                                         spread_return=float(ls_return), rf_return=float(rf_return),
                                         funded_return=float(funded_return)))
            for representation, observed in [('spread', spread), ('funded', funded)]:
                record = metric_record(observed, spread, weighting, rule, representation, evaluation_index)
                record.update(calibration_spread_mean=float(calibration_returns.mean()),
                              calibration_spread_sd=float(calibration_returns.std(ddof=1)),
                              calibration_spread_h=float(calibration_returns.mean() / calibration_returns.std(ddof=1)),
                              sum_weights=float(vector.sum()), max_weight=float(vector.max()),
                              positive_weights=int((vector > 1e-8).sum()))
                statistics_rows.append(record)

    if config_path.read_bytes() != config_bytes:
        raise RuntimeError('Exploratory design changed during the run')
    tables = ROOT / 'tables'
    tables.mkdir(exist_ok=True)
    paths = {
        'weights': tables / 'exploratory_combination_weights.csv',
        'monthly_returns': tables / 'exploratory_combination_monthly_returns.csv',
        'statistics': tables / 'exploratory_combination_statistics.csv',
    }
    for key, rows in [('weights', weight_rows), ('monthly_returns', monthly_rows), ('statistics', statistics_rows)]:
        pd.DataFrame(rows).to_csv(paths[key], index=False)
    stats = pd.DataFrame(statistics_rows)
    metadata.update(
        status='complete', completed_utc=datetime.now(timezone.utc).isoformat(),
        elapsed_seconds=time.monotonic() - started, calibration_months=144,
        evaluation_months=108, strategies=194,
        output_rows=dict(weights=len(weight_rows), monthly_returns=len(monthly_rows), statistics=len(statistics_rows)),
        output_sha256={key: sha256(path.read_bytes()).hexdigest() for key, path in paths.items()},
        highest_combination_zero_h=float(stats['zero_h'].max()),
        combinations_reaching_fund_x_zero_h=int((stats['zero_h'] >= metadata['fund_x_common_zero_h']).sum()),
        highest_combination_excess_sharpe=float(stats['excess_sharpe'].max()),
        combinations_reaching_fund_x_excess_sharpe=int((stats['excess_sharpe'] >= metadata['fund_x_common_excess_sharpe']).sum()),
        checks=dict(calibration_gradient_independent=True, unchanged_observed_months=True,
                    weights_constraints_pass=True, scalar_monthly_returns_match=True,
                    cash_addition_matches=True),
    )
    metadata_path.write_text(json.dumps(metadata, indent=2) + '\n')
    print(stats[['weighting', 'rule', 'representation', 'zero_h', 'excess_sharpe',
                 'B', 'normal_p', 'conventional_any']].to_string(index=False))
    print(json.dumps(metadata, indent=2))


if __name__ == '__main__':
    main()
