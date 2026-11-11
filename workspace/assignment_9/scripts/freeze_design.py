"""Freeze the analysis choices before computing any screening outcomes."""
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
import json

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]


def main():
    original = pd.read_parquet(ROOT / 'data/raw/PredictorLSretWide.parquet')
    original = original.set_index(pd.to_datetime(original['date']).dt.to_period('M')).drop(columns='date') / 100
    alternate = pd.read_parquet(ROOT / 'data/raw/PredictorVWforce.parquet')
    alternate = alternate.loc[alternate['port'] == 'LS'].copy()
    alternate['month'] = pd.to_datetime(alternate['date']).dt.to_period('M')
    alternate = alternate.pivot(index='month', columns='signalname', values='ret') / 100
    dates = pd.period_range('1980-01', '2025-12', freq='M')
    original = original.reindex(dates)
    alternate = alternate.reindex(dates)
    descriptive = sorted(original.columns[original.loc['2017-01':'2025-12'].notna().all()])
    core = sorted(set(descriptive) & set(original.columns[original.loc['2005-01':'2016-12'].notna().all()]))
    vw_core = sorted(set(core) & set(alternate.columns[alternate.loc['2005-01':'2025-12'].notna().all()]))
    doc = pd.read_csv(ROOT / 'data/raw/SignalDoc.csv')
    metadata = doc.set_index('Acronym').loc[descriptive]
    assert (metadata['Cat.Signal'] == 'Predictor').all()
    assert metadata['Year'].max() <= 2016
    assert metadata['SampleEndYear'].max() <= 2014
    spec = dict(
        assignment=9, frozen_utc=datetime.now(timezone.utc).isoformat(),
        status='frozen before screening results', seed=20261111,
        data_release='2026.10', dataset_commit='dd1054254c4501776432caa6d7ce5ecd9586f6a9',
        return_units='decimal simple returns after dividing published percent returns by100 exactly once',
        primary_return='original-paper long-short stock return spread, with no second RF subtraction',
        funded_sensitivity='RF + one unit of LS payoff per unit of collateral, gross long+short notional2; no execution, borrowing or management costs deducted by source',
        weighting_sensitivity='value weighting forced while retaining original portfolio sorts',
        descriptive_signals=descriptive, core_signals=core, vw_core_signals=vw_core,
        latest_common_month='2025-12', descriptive_start='2017-01', months_common=108,
        development=['1980-01','2004-12'], calibration=['2005-01','2016-12'], evaluation=['2017-01','2025-12'],
        window_lengths=[108,60], primary_window=108,
        development_windows='all December-end trailing windows wholly inside development period, finite complete histories only',
        evaluation_windows='all December-end trailing windows wholly inside evaluation period; common108 snapshot is primary',
        cutoff_fit='joint circular time-block bootstrap of entire calibration matrix; one ordinary-reference95th percentile and one common selection-reference maximum95th percentile',
        bootstrap=dict(calibration_draws=5000, evaluation_draws=1000, power_interval_draws=500,
                       primary_block_months=12, sensitivity_block_months=6,
                       sensitivity_calibration_draws=3000, sensitivity_evaluation_draws=500,
                       reference_is_conditional_historical=True),
        rank_statistic='mean(LS)/sampleSD(LS) for raw and funded versions; alphabetical acronym breaks exact ties',
        candidate_pool_sizes=[1,5,20,50,100,'all'], calibration_pool_sizes=[1,5,20,50,100,'all'],
        exact_selection='uniform K-subset without replacement from fixed observed portfolio set; highest historical Sharpe wins; rank-j probability C(N-j,K-1)/C(N,K)',
        conventional_rules={'bias':'B>2','normal_count':'fitted-normal lower binomial tail<.05','combined':'either conventional rule'},
        diagnostic_score='C=max(fixed development empiricalCDF(B),fixed development empiricalCDF(D)); ranks are not p-values',
        calibrated_rules=['ordinary_reference','selection_reference'], cutoff_exceedance='strict>',
        zero_rule='B numerator[0,SD], lower[-SD,0), denominator+1, negative count strictly<0',
        reporting=dict(primary_target_gain=.0005, loss_magnitudes=[.005,.01,.02],
                       hide_probabilities=[1.,.5], recognition_lags=['permanent',1,3,6],
                       warmup_months=6, settlement_audit_months=6,
                       spread_ledger='additive payoff gap q=target-F; F*=F+q-q_lag; eligibility from underlying current F only',
                       funded_ledger='logNAV gap q=log1p(target)-log1p(R); apply to RF+LS with positive1+R',
                       uncertainty_primary='joint time-block bootstrap; no independent-binomial intervals across strategies',
                       probability_sensitivity_draws=100, uniform_target_sensitivity=[0.,.001],
                       secondary_selected_policy='one altered candidate included with K-1 randomly sampled unaltered candidates; selection probability, joint alert and conditional alert separately'),
        smoothing_sensitivity=dict(lambdas=[.25,.5,.75], formula='(1-lambda)*current + lambda*previous', interpretation='symmetric reporting sensitivity; intent is not identified'),
        regression='descriptive fixed ridge logit on standardized Sharpe, skewness, kurtosis and ACF1; joint-month bootstrap uncertainty, no causal interpretation',
        no_mean_matching=True, missing_values='retain missing; no zero fill; fixed complete-case cohorts described above',
        actual_fraud_labels=False,
        inference_limits=[
            'Unmodified reconstructed-benchmark alerts, not a measured rate of dishonest fund reporting.',
            'Current factor catalogue, signs and implementations are retrospective; original papers predate2017.',
            'Time-bootstrap results are conditional on the historical reference and can fail in the held-out period.',
            'Factor histories share stocks and market months; repetitions and overlapping windows are dependent.',
            'The literature-selected catalogue and complete-case cohorts are not a representative fund universe.',
            'Fund X performance outside benchmark support must remain visible without shifting benchmark means.'
        ],
    )
    target = ROOT / 'data/frozen_design.json'
    if target.exists():
        raise RuntimeError('Design already frozen; preserve the existing record')
    target.write_text(json.dumps(spec, indent=2)+'\n', encoding='utf-8')
    for label, frame, names in [('original', original, core), ('value_weighted', alternate, vw_core)]:
        frame[names].to_csv(ROOT / f'data/{label}_decimal_panel.csv', index_label='month')
    print(json.dumps(dict(design_sha256=sha256(target.read_bytes()).hexdigest(),
                         descriptive=len(descriptive), original_core=len(core), value_weighted_core=len(vw_core)), indent=2))


if __name__ == '__main__':
    main()
