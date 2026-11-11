"""Load the frozen portfolio-level inputs with explicit return conventions."""
from io import StringIO
from pathlib import Path
import json

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]


def read_design():
    return json.loads((ROOT / 'data/frozen_design.json').read_text())


def read_french():
    text = (ROOT / 'data/raw/F-F_Research_Data_Factors.csv').read_text()
    rows = []
    for line in text.splitlines():
        first = line.split(',')[0].strip()
        if len(first) == 6 and first.isdigit():
            rows.append(line)
    frame = pd.read_csv(StringIO('yyyymm,Mkt-RF,SMB,HML,RF\n'+'\n'.join(rows)))
    frame.index = pd.PeriodIndex(frame.pop('yyyymm').astype(str), freq='M')
    if frame.index.has_duplicates:
        raise ValueError('Duplicate French monthly dates')
    return frame.astype(float) / 100


def load_panel(weighting='original', descriptive=False):
    design = read_design()
    if weighting == 'original':
        frame = pd.read_parquet(ROOT / 'data/raw/PredictorLSretWide.parquet')
        frame.index = pd.to_datetime(frame.pop('date')).dt.to_period('M')
    elif weighting == 'value_weighted':
        long = pd.read_parquet(ROOT / 'data/raw/PredictorVWforce.parquet')
        long = long.loc[long['port'] == 'LS'].copy()
        long['month'] = pd.to_datetime(long['date']).dt.to_period('M')
        frame = long.pivot(index='month', columns='signalname', values='ret')
    else:
        raise ValueError('Unknown portfolio weighting')
    if frame.index.has_duplicates:
        raise ValueError('Duplicate portfolio month')
    columns = design['descriptive_signals'] if descriptive else design['core_signals']
    if weighting == 'value_weighted' and not descriptive:
        columns = design['vw_core_signals']
    frame = frame.sort_index().reindex(pd.period_range('1980-01', '2025-12', freq='M'))
    return frame.loc[:, columns].astype(float) / 100


def load_fund_x():
    frame = pd.read_csv(ROOT / 'data/raw/fund_x_2017_01_to_2026_09.csv')
    values = pd.Series(frame['lsq_return'].to_numpy(), index=pd.PeriodIndex(frame['date'], freq='M'), name='Fund X')
    if values.index.has_duplicates or not np.isfinite(values).all():
        raise ValueError('Invalid frozen Fund X series')
    return values


def phase_arrays(weighting, phase):
    frame = load_panel(weighting)
    start, end = read_design()[phase]
    frame = frame.loc[start:end]
    rf = read_french().reindex(frame.index)['RF']
    if not np.isfinite(rf).all():
        raise ValueError('Missing risk-free month')
    return frame, rf


def circular_indices(rng, histories, length, source_length, block):
    blocks = (length+block-1)//block
    starts = rng.integers(0, source_length, size=(histories, blocks))
    indices = (starts[:, :, None]+np.arange(block)) % source_length
    return indices.reshape(histories, -1)[:, :length]


def year_end_windows(frame, length):
    """Return only complete per-strategy windows ending in December."""
    for end in range(length-1, len(frame)):
        if frame.index[end].month != 12:
            continue
        history = frame.iloc[end-length+1:end+1]
        good = history.notna().all()
        if good.any():
            yield frame.index[end], history.loc[:, good]
