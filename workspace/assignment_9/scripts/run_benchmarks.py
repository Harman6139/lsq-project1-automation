"""Chronologically separated selection/calibration analysis of observed portfolios."""
from hashlib import sha256
from pathlib import Path
import argparse
import json
import time

import numpy as np
import pandas as pd

from a9_data import ROOT, circular_indices, load_panel, phase_arrays, read_design, read_french, year_end_windows
from a9_metrics import combined_scores, fit_score_maps, raw_scores, weighted_quantile, winner_weights


def pool_sizes(n):
    return sorted(set(min(n, x) for x in [1, 5, 20, 50, 100, n]))


def cache_dependencies(weighting):
    raw_file = 'PredictorLSretWide.parquet' if weighting == 'original' else 'PredictorVWforce.parquet'
    paths = [ROOT / 'data/frozen_design.json', ROOT / 'data/source_provenance.json',
             ROOT / 'data/raw' / raw_file, ROOT / 'data/raw/F-F_Research_Data_Factors.csv',
             ROOT / 'scripts/a9_data.py', ROOT / 'scripts/a9_metrics.py',
             ROOT / 'scripts/run_benchmarks.py']
    return {path.relative_to(ROOT).as_posix(): sha256(path.read_bytes()).hexdigest() for path in paths}


def development_maps(weighting, length):
    folder = ROOT / 'data/maps'
    folder.mkdir(exist_ok=True)
    paths = {kind: folder / f'{weighting}_{kind}_{length}.npz' for kind in ['spread', 'funded']}
    metadata_path = folder / f'{weighting}_{length}.json'
    metrics_hash = sha256((ROOT / 'scripts/a9_metrics.py').read_bytes()).hexdigest()
    dependencies = cache_dependencies(weighting)
    if metadata_path.exists() and all(path.exists() for path in paths.values()):
        metadata = json.loads(metadata_path.read_text())
        if metadata['metrics_sha256'] != metrics_hash or metadata.get('dependencies') != dependencies:
            raise RuntimeError('Existing development map uses different score code')
        return {kind: load_maps(path) for kind, path in paths.items()}
    frame, rf = phase_arrays(weighting, 'development')
    scores = {kind: {'B': [], 'D': []} for kind in paths}
    records = []
    strategies = set()
    for end, history in year_end_windows(frame, length):
        strategies.update(history.columns)
        for kind in paths:
            observed = history.to_numpy().T
            if kind == 'funded':
                observed = observed + rf.reindex(history.index).to_numpy()[None, :]
            point = raw_scores(observed)
            for field in ['B', 'D']:
                scores[kind][field].append(point[field])
        records.append(dict(end=str(end), strategies=history.shape[1]))
    for kind, path in paths.items():
        B, D = fit_score_maps(np.concatenate(scores[kind]['B']), np.concatenate(scores[kind]['D']))
        np.savez_compressed(path, B=B, D=D)
    metadata = dict(weighting=weighting, months=length, metrics_sha256=metrics_hash, dependencies=dependencies,
                    records=sum(x['strategies'] for x in records),
                    unique_strategies=len(strategies), endpoints=records)
    metadata_path.write_text(json.dumps(metadata, indent=2)+'\n')
    return {kind: load_maps(path) for kind, path in paths.items()}


def load_maps(path):
    with np.load(path) as saved:
        return saved['B'].copy(), saved['D'].copy()


def score_cache(weighting, phase, length, block, draws, maps):
    folder = ROOT / 'data/score_cache'
    folder.mkdir(exist_ok=True)
    target = folder / f'{weighting}_{phase}_{length}_b{block}.npz'
    metadata_path = target.with_suffix('.json')
    dependency_hashes = cache_dependencies(weighting)
    for kind in maps:
        path = ROOT / f'data/maps/{weighting}_{kind}_{length}.npz'
        dependency_hashes[path.relative_to(ROOT).as_posix()] = sha256(path.read_bytes()).hexdigest()
    expected = dict(weighting=weighting, phase=phase, length=length, block=block, draws=draws,
                    dependencies=dependency_hashes)
    if target.exists():
        if json.loads(metadata_path.read_text()) != expected:
            raise RuntimeError(f'Existing score cache has different settings: {target.name}')
        with np.load(target) as saved:
            return {name: saved[name].copy() for name in saved.files}
    frame, rf = phase_arrays(weighting, phase)
    if frame.isna().any().any():
        raise ValueError('Bootstrap reference must be a complete frozen matrix')
    source = frame.to_numpy()
    cash = rf.to_numpy()
    n = frame.shape[1]
    result = {f'{kind}_{field}': np.empty((draws, n))
              for kind in ['spread', 'funded'] for field in ['B', 'D', 'C', 'P']}
    result['rank_h'] = np.empty((draws, n))
    stage = 1 if phase == 'calibration' else 2
    rng = np.random.default_rng(np.random.SeedSequence([read_design()['seed'], stage, length, block]))
    for start in range(0, draws, 25):
        stop = min(start+25, draws)
        indices = circular_indices(rng, stop-start, length, len(source), block)
        observed = source[indices].transpose(0, 2, 1).reshape(-1, length)
        rank = raw_scores(observed)
        result['rank_h'][start:stop] = rank['sharpe'].reshape(-1, n)
        for kind in ['spread', 'funded']:
            values = observed
            if kind == 'funded':
                values = observed + np.repeat(cash[indices], n, axis=0)
            point = rank if kind == 'spread' else raw_scores(values)
            for field in ['B', 'D']:
                result[f'{kind}_{field}'][start:stop] = point[field].reshape(-1, n)
            result[f'{kind}_P'][start:stop] = point['normal_p'].reshape(-1, n)
            result[f'{kind}_C'][start:stop] = combined_scores(point['B'], point['D'], maps[kind]).reshape(-1, n)
    with target.open('wb') as out:
        np.savez_compressed(out, **result)
    metadata_path.write_text(json.dumps(expected, indent=2)+'\n')
    return result


def fit_cutoffs(pack, kind):
    scores = pack[f'{kind}_C']
    n = scores.shape[1]
    ranks = np.argsort(-pack['rank_h'], axis=1, kind='stable')
    ordered = np.take_along_axis(scores, ranks, axis=1)
    rows = []
    for k in pool_sizes(n):
        weights = np.broadcast_to(winner_weights(n, k), ordered.shape)
        cutoff = weighted_quantile(ordered.ravel(), weights.ravel(), quantile=.95)
        rows.append(dict(K=k, cutoff=float(cutoff)))
    return dict(ordinary=rows[0]['cutoff'], selection=max(x['cutoff'] for x in rows), per_pool=rows)


def decisions(B, normal_p, C, cutoffs):
    return {
        'conventional_bias': B > 2,
        'conventional_normal': normal_p < .05,
        'conventional_any': (B > 2) | (normal_p < .05),
        'ordinary_calibrated': C > cutoffs['ordinary'],
        'selection_calibrated': C > cutoffs['selection'],
    }


def point_decisions(point, C, cutoffs):
    return decisions(point['B'], point['normal_p'], C, cutoffs)


def reference_decisions(pack, kind, cutoffs):
    return decisions(pack[f'{kind}_B'], pack[f'{kind}_P'], pack[f'{kind}_C'], cutoffs)


def weighted_rates(flags, rank_h):
    flags = np.atleast_2d(flags)
    rank_h = np.atleast_2d(rank_h)
    order = np.argsort(-rank_h, axis=1, kind='stable')
    ranked = np.take_along_axis(flags, order, axis=1)
    n = ranked.shape[1]
    return {k: ranked @ winner_weights(n, k) for k in pool_sizes(n)}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--weighting', choices=['original', 'value_weighted'], required=True)
    args = parser.parse_args()
    started = time.monotonic()
    design = read_design()
    tables = ROOT / 'tables'
    tables.mkdir(exist_ok=True)
    cutoff_rows = []
    observed_rows = []
    uncertainty_rows = []
    calibration_rows = []
    for length in design['window_lengths']:
        maps = development_maps(args.weighting, length)
        for block in [12, 6]:
            n_cal = design['bootstrap']['calibration_draws'] if block == 12 else design['bootstrap']['sensitivity_calibration_draws']
            n_eval = design['bootstrap']['evaluation_draws'] if block == 12 else design['bootstrap']['sensitivity_evaluation_draws']
            calibration = score_cache(args.weighting, 'calibration', length, block, n_cal, maps)
            evaluation = score_cache(args.weighting, 'evaluation', length, block, n_eval, maps)
            for kind in ['spread', 'funded']:
                cutoffs = fit_cutoffs(calibration, kind)
                for row in cutoffs['per_pool']:
                    cutoff_rows.append(dict(weighting=args.weighting, representation=kind, months=length,
                                            block=block, ordinary_cutoff=cutoffs['ordinary'],
                                            selection_cutoff=cutoffs['selection'], **row))
                for phase, pack in [('calibration', calibration), ('evaluation', evaluation)]:
                    flags = reference_decisions(pack, kind, cutoffs)
                    for method, alerts in flags.items():
                        rates = weighted_rates(alerts, pack['rank_h'])
                        differences = {k: value-rates[1] for k, value in rates.items()}
                        for k, values in rates.items():
                            record = dict(weighting=args.weighting, representation=kind, months=length,
                                          block=block, phase=phase, method=method, K=k, draws=len(values),
                                          mean_rate=float(values.mean()), median_rate=float(np.median(values)),
                                          lo=float(np.quantile(values,.025)), hi=float(np.quantile(values,.975)),
                                          mean_change=float(differences[k].mean()),
                                          change_lo=float(np.quantile(differences[k],.025)),
                                          change_hi=float(np.quantile(differences[k],.975)))
                            (calibration_rows if phase == 'calibration' else uncertainty_rows).append(record)
                if block != 12:
                    continue
                frame, rf = phase_arrays(args.weighting, 'evaluation')
                for end, history in year_end_windows(frame, length):
                    raw = history.to_numpy().T
                    rank_h = raw.mean(axis=1)/raw.std(axis=1,ddof=1)
                    returns = raw if kind == 'spread' else raw+rf.reindex(history.index).to_numpy()[None,:]
                    scores = raw_scores(returns)
                    C = combined_scores(scores['B'],scores['D'],maps[kind])
                    for method, alerts in point_decisions(scores,C,cutoffs).items():
                        for k, rate in weighted_rates(alerts,rank_h).items():
                            observed_rows.append(dict(weighting=args.weighting,representation=kind,months=length,
                                                      end=str(end),method=method,K=k,n_strategies=len(alerts),
                                                      alert_count=int(alerts.sum()),rate=float(rate[0])))
                print(json.dumps(dict(stage='cutoffs_locked',weighting=args.weighting,months=length,
                                      representation=kind,ordinary=cutoffs['ordinary'],selection=cutoffs['selection'])),flush=True)
    for name, rows in [('cutoffs',cutoff_rows),('observed_selection',observed_rows),
                       ('bootstrap_validation',uncertainty_rows),('bootstrap_calibration',calibration_rows)]:
        pd.DataFrame(rows).to_csv(tables/f'{name}_{args.weighting}.csv',index=False)
    print(json.dumps(dict(status='complete',weighting=args.weighting,seconds=time.monotonic()-started)),flush=True)


if __name__ == '__main__':
    main()
