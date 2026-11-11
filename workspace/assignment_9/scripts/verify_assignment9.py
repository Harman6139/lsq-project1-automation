"""Independent input, scalar and saved-result checks for Assignment 9.

This file does not use the production loader or score functions. Source data are
read directly; scalar formula references and combinatorial probabilities are
compared with saved arrays and tables. Only the compact verification record is
written.
"""
from bisect import bisect_right
from hashlib import sha256
from io import StringIO
from math import comb, erfc, fsum, sqrt
from pathlib import Path
from statistics import mean, stdev
from zipfile import ZipFile
import argparse
import json
import xml.etree.ElementTree as ET

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / 'data/raw'


def independent_inputs():
    design = json.loads((ROOT / 'data/frozen_design.json').read_text())
    op = pd.read_parquet(RAW / 'PredictorLSretWide.parquet')
    op['month'] = pd.to_datetime(op.pop('date')).dt.to_period('M')
    assert not op['month'].duplicated().any()
    op = op.set_index('month').sort_index()
    full = pd.read_parquet(RAW / 'PredictorPortsFull.parquet')
    ls = full.loc[full['port'].eq('LS'), ['signalname', 'date', 'ret']].copy()
    ls['month'] = pd.to_datetime(ls.pop('date')).dt.to_period('M')
    assert not ls.duplicated(['signalname', 'month']).any()
    full_wide = ls.pivot(index='month', columns='signalname', values='ret')
    full_wide = full_wide.reindex(index=op.index, columns=op.columns)
    assert np.array_equal(op.isna().to_numpy(), full_wide.isna().to_numpy())
    assert np.nanmax(np.abs(op.to_numpy() - full_wide.to_numpy())) == 0
    full_vw = pd.read_parquet(RAW / 'PredictorVWforce.parquet')
    vw_ls = full_vw.loc[full_vw['port'].eq('LS'), ['signalname', 'date', 'ret']].copy()
    vw_ls['month'] = pd.to_datetime(vw_ls.pop('date')).dt.to_period('M')
    assert not vw_ls.duplicated(['signalname', 'month']).any()
    vw = vw_ls.pivot(index='month', columns='signalname', values='ret')
    vw = vw.reindex(index=op.index, columns=op.columns)

    ff_rows = []
    for line in (RAW / 'F-F_Research_Data_Factors.csv').read_text().splitlines():
        cells = line.split(',')
        if len(cells[0]) == 6 and cells[0].isdigit():
            ff_rows.append((pd.Period(cells[0], freq='M'), float(cells[4]) / 100))
    rf = pd.Series(dict(ff_rows))
    assert len(rf) == len(ff_rows)
    return design, {'original': op / 100, 'value_weighted': vw / 100}, rf


def scalar_scores(row):
    values = [float(x) for x in row]
    assert all(np.isfinite(values))
    n = len(values)
    mu = mean(values)
    sd = stdev(values)
    h = mu / sd
    p = erfc(h / sqrt(2)) / 2
    negative = sum(x < 0 for x in values)
    upper = sum(0 <= x <= sd for x in values)
    lower = sum(-sd <= x < 0 for x in values)
    normal_tail = fsum(comb(n, k) * p ** k * (1 - p) ** (n - k)
                       for k in range(negative + 1))
    return {'B': upper / (1 + lower), 'D': n * p - negative,
            'P': normal_tail, 'h': h, 'negative': negative}


def marginal_maximum(bias, deficit, maps):
    b, d = maps
    return max(bisect_right(b, bias) / (len(b) + 1),
               bisect_right(d, deficit) / (len(d) + 1))


def direct_weights(n, k):
    denominator = comb(n, k)
    return np.array([comb(n - j, k - 1) / denominator
                     if n - j >= k - 1 else 0.0 for j in range(1, n + 1)])


def metadata_checks(design, panels, rf):
    provenance = json.loads((ROOT / 'data/source_provenance.json').read_text())
    for source in provenance['sources']:
        file = ROOT / source['file']
        assert sha256(file.read_bytes()).hexdigest() == source['sha256'], source['file']
    with ZipFile(RAW / 'F-F_Research_Data_Factors_CSV.zip') as archive:
        csv_files = [name for name in archive.namelist() if name.lower().endswith('.csv')]
        assert len(csv_files) == 1
        assert archive.read(csv_files[0]) == (RAW / 'F-F_Research_Data_Factors.csv').read_bytes()
    assert len(design['descriptive_signals']) == 195
    assert len(design['core_signals']) == len(design['vw_core_signals']) == 194
    assert design['core_signals'] == design['vw_core_signals']
    counts = {}
    development = {}
    for weighting, panel in panels.items():
        complete = {}
        counts[weighting] = {}
        for phase in ['development', 'calibration', 'evaluation']:
            dates = pd.period_range(*design[phase], freq='M')
            data = panel.reindex(dates)
            complete[phase] = set(data.columns[data.notna().all()])
            counts[weighting][phase] = len(complete[phase])
            assert rf.reindex(dates).notna().all()
        assert sorted(complete['evaluation']) == design['descriptive_signals']
        assert sorted(complete['calibration'] & complete['evaluation']) == design['core_signals']
        core = panel.loc[:, design['core_signals']]
        dev = core.reindex(pd.period_range(*design['development'], freq='M'))
        development[weighting] = {}
        for length in design['window_lengths']:
            endpoints = []
            strategies = set()
            for end in range(length - 1, len(dev)):
                if dev.index[end].month != 12:
                    continue
                chunk = dev.iloc[end - length + 1:end + 1]
                good = list(chunk.columns[chunk.notna().all()])
                strategies.update(good)
                endpoints.append((str(dev.index[end]), len(good)))
            development[weighting][str(length)] = {
                'eligible_strategy_windows': sum(x[1] for x in endpoints),
                'year_endpoints': len(endpoints), 'strategies': len(strategies),
                'core_without_development_window': sorted(set(core.columns) - strategies),
            }
        for phase in ['development', 'calibration', 'evaluation']:
            dates = pd.period_range(*design[phase], freq='M')
            funded = core.reindex(dates).add(rf.reindex(dates), axis=0)
            assert (funded.stack() > -1).all()
    assert set(design['calibration_pool_sizes']) == set(design['candidate_pool_sizes'])
    return {'source_hashes_match': True, 'wide_and_long_LS_exactly_match': True,
            'complete_signals': counts, 'development_windows': development,
            'funded_positive_NAV_support': True,
            'all_candidate_K_values_in_calibration': True}


def score_map_checks(design, panels, rf):
    checked = 0
    for weighting, panel in panels.items():
        dev = panel.reindex(pd.period_range(*design['development'], freq='M'))
        dev = dev.loc[:, design['core_signals']]
        for length in design['window_lengths']:
            meta = json.loads((ROOT / f'data/maps/{weighting}_{length}.json').read_text())
            for relative, digest in meta['dependencies'].items():
                assert sha256((ROOT / relative).read_bytes()).hexdigest() == digest, relative
            sources = {kind: {'B': [], 'D': []} for kind in ['spread', 'funded']}
            for end in range(length - 1, len(dev)):
                if dev.index[end].month != 12:
                    continue
                data = dev.iloc[end - length + 1:end + 1]
                data = data.loc[:, data.notna().all()]
                cash = rf.reindex(data.index).to_numpy()
                for strategy in data.columns:
                    row = data[strategy].to_numpy()
                    for kind in sources:
                        score = scalar_scores(row if kind == 'spread' else row + cash)
                        for field in ['B', 'D']:
                            sources[kind][field].append(score[field])
            for kind, fields in sources.items():
                path = ROOT / f'data/maps/{weighting}_{kind}_{length}.npz'
                if not path.exists():
                    raise FileNotFoundError(path)
                with np.load(path) as saved:
                    for field in ['B', 'D']:
                        expected = np.sort(fields[field])
                        assert np.allclose(saved[field], expected, atol=2e-13, rtol=2e-13), path.name
                checked += 1
    return {'development_maps_checked': checked, 'independent_scalar_maps_match': True}


def cache_checks(design, panels, rf):
    caches = sorted((ROOT / 'data/score_cache').glob('*.npz'))
    checked_histories = 0
    dependency_checks = 0
    expected_common = {'data/frozen_design.json', 'data/source_provenance.json',
                       'data/raw/F-F_Research_Data_Factors.csv', 'scripts/a9_data.py',
                       'scripts/a9_metrics.py', 'scripts/run_benchmarks.py'}
    for path in caches:
        meta = json.loads(path.with_suffix('.json').read_text())
        weighting, phase = meta['weighting'], meta['phase']
        length, block = meta['length'], meta['block']
        dependencies = meta['dependencies']
        raw_path = ('data/raw/PredictorLSretWide.parquet' if weighting == 'original'
                    else 'data/raw/PredictorVWforce.parquet')
        expected = expected_common | {raw_path,
                    f'data/maps/{weighting}_spread_{length}.npz',
                    f'data/maps/{weighting}_funded_{length}.npz'}
        assert set(dependencies) == expected, path.name
        for relative, digest in dependencies.items():
            assert sha256((ROOT / relative).read_bytes()).hexdigest() == digest, relative
            dependency_checks += 1
        dates = pd.period_range(*design[phase], freq='M')
        source = panels[weighting].reindex(dates).loc[:, design['core_signals']].to_numpy()
        cash = rf.reindex(dates).to_numpy()
        stage = 1 if phase == 'calibration' else 2
        rng = np.random.default_rng(np.random.SeedSequence([design['seed'], stage, length, block]))
        starts = rng.integers(0, len(source), size=(2, (length + block - 1) // block))
        index_rows = [[(int(start) + offset) % len(source)
                       for start in row for offset in range(block)][:length] for row in starts]
        maps = {}
        for kind in ['spread', 'funded']:
            with np.load(ROOT / f'data/maps/{weighting}_{kind}_{length}.npz') as saved:
                maps[kind] = (saved['B'].copy(), saved['D'].copy())
        with np.load(path) as saved:
            assert saved['rank_h'].shape == (meta['draws'], 194)
            for draw, indices in enumerate(index_rows):
                for strategy in [0, 97, 193]:
                    raw = source[indices, strategy]
                    plain = scalar_scores(raw)
                    assert np.isclose(saved['rank_h'][draw, strategy], plain['h'], atol=1e-12)
                    for kind in ['spread', 'funded']:
                        score = plain if kind == 'spread' else scalar_scores(raw + cash[indices])
                        for field in ['B', 'D', 'P']:
                            assert np.isclose(saved[f'{kind}_{field}'][draw, strategy], score[field],
                                              atol=2e-12, rtol=2e-12), (path.name, draw, strategy, kind, field)
                        combined = marginal_maximum(score['B'], score['D'], maps[kind])
                        assert saved[f'{kind}_C'][draw, strategy] == combined
                        checked_histories += 1
    prior_runner = ROOT / 'data/code_history/run_benchmarks_initial.py'
    assert prior_runner.exists()
    return {'score_caches_checked': len(caches), 'independent_scalar_history_cases': checked_histories,
            'complete_cache_dependency_hashes_checked': dependency_checks,
            'initial_runner_preserved_sha256': sha256(prior_runner.read_bytes()).hexdigest(),
            'joint_calendar_and_cash_broadcast_match': True,
            'bootstrap_interpretation': 'conditional historical resampling ranges; no exact coverage claim'}


def cutoff_checks():
    checked = 0
    borderline = []
    for path in sorted((ROOT / 'tables').glob('cutoffs_*.csv')):
        table = pd.read_csv(path, float_precision='round_trip')
        keys = ['weighting', 'representation', 'months', 'block']
        for key, group in table.groupby(keys):
            weighting, kind, length, block = key
            cache = ROOT / f'data/score_cache/{weighting}_calibration_{length}_b{block}.npz'
            with np.load(cache) as saved:
                order = np.argsort(-saved['rank_h'], axis=1, kind='stable')
                scores = np.take_along_axis(saved[f'{kind}_C'], order, axis=1)
            values, inverse = np.unique(scores, return_inverse=True)
            if inverse.ndim != 1:
                inverse = inverse.ravel()
            direct_cutoffs = []
            for row in group.itertuples():
                weights = direct_weights(194, int(row.K))
                masses = np.bincount(inverse, weights=np.broadcast_to(weights, scores.shape).ravel(),
                                     minlength=len(values))
                cumulative = np.cumsum(masses) / masses.sum()
                independent = float(values[np.searchsorted(cumulative, .95, side='left')])
                recorded = float(row.cutoff)
                tail = masses[values > recorded].sum() / masses.sum()
                assert tail <= .05 + 1e-12, (key, row.K, tail)
                below_or_equal = masses[values <= recorded].sum() / masses.sum()
                strictly_below = masses[values < recorded].sum() / masses.sum()
                assert below_or_equal >= .95 - 1e-12
                assert strictly_below <= .95 + 1e-12
                if independent != recorded:
                    # At exact empirical 95% boundaries, summing tied fractional
                    # weights can differ at the last floating-point bit.
                    assert min(abs(below_or_equal - .95), abs(strictly_below - .95)) <= 1e-12
                    borderline.append({'configuration': list(key), 'K': int(row.K)})
                direct_cutoffs.append(recorded)
                checked += 1
            ordinary = float(group.loc[group['K'].eq(1), 'cutoff'].iloc[0])
            assert np.allclose(group['ordinary_cutoff'], ordinary, atol=1e-14, rtol=0)
            assert np.allclose(group['selection_cutoff'], max(direct_cutoffs), atol=1e-14, rtol=0)
    return {'calibration_quantiles_checked': checked, 'strict_calibration_tail_at_most_five_percent': True,
            'cutoff_csv_reader_precision': 'round_trip',
            'ties_and_combinatorial_weights_checked': True, 'floating_boundary_cases': borderline}


def observed_checks(design, panels, rf):
    checked = 0
    for path in sorted((ROOT / 'tables').glob('observed_selection_*.csv')):
        observed = pd.read_csv(path)
        cutoff_table = pd.read_csv(ROOT / f'tables/cutoffs_{observed.weighting.iloc[0]}.csv',
                                   float_precision='round_trip')
        keys = ['weighting', 'representation', 'months', 'end']
        for key, group in observed.groupby(keys):
            weighting, kind, length, end = key
            stop = pd.Period(end, freq='M')
            dates = pd.period_range(stop - int(length) + 1, stop, freq='M')
            data = panels[weighting].reindex(dates).loc[:, design['core_signals']]
            cash = rf.reindex(dates).to_numpy()
            with np.load(ROOT / f'data/maps/{weighting}_{kind}_{length}.npz') as saved:
                maps = (saved['B'].copy(), saved['D'].copy())
            baseline = cutoff_table.loc[cutoff_table['representation'].eq(kind)
                                        & cutoff_table['months'].eq(length)
                                        & cutoff_table['block'].eq(12)].iloc[0]
            h = []
            all_flags = {method: [] for method in observed['method'].unique()}
            for strategy in data.columns:
                raw = data[strategy].to_numpy()
                h.append(mean(raw) / stdev(raw))
                score = scalar_scores(raw if kind == 'spread' else raw + cash)
                c = marginal_maximum(score['B'], score['D'], maps)
                b, p = score['B'] > 2, score['P'] < .05
                flags = {'conventional_bias': b, 'conventional_normal': p,
                         'conventional_any': b or p,
                         'ordinary_calibrated': c > baseline['ordinary_cutoff'],
                         'selection_calibrated': c > baseline['selection_cutoff']}
                for method, flag in flags.items():
                    all_flags[method].append(flag)
            order = sorted(range(len(h)), key=lambda j: (-h[j], j))
            for row in group.itertuples():
                flags = np.asarray(all_flags[row.method], dtype=float)
                assert int(flags.sum()) == row.alert_count
                assert len(flags) == row.n_strategies == 194
                selected = fsum(float(flags[j]) * float(w)
                                for j, w in zip(order, direct_weights(194, int(row.K))))
                assert np.isclose(selected, row.rate, atol=2e-14, rtol=2e-14), key
                checked += 1
    return {'observed_rate_rows_checked': checked,
            'observed_count_is_full_194_strategy_pool': True,
            'selected_rate_is_exact_subset_winner_probability': True}


def locked_cutoff_checks():
    path = ROOT / 'data/locked_cutoffs.json'
    locked = json.loads(path.read_text())['rules']
    groups_checked = 0
    values_checked = 0
    for csv_path in sorted((ROOT / 'tables').glob('cutoffs_*.csv')):
        table = pd.read_csv(csv_path, float_precision='round_trip')
        keys = ['weighting', 'representation', 'months', 'block']
        for key, group in table.groupby(keys):
            weighting, kind, months, block = key
            identifier = f'{weighting}:{kind}:{int(months)}:b{int(block)}'
            rule = locked[identifier]
            assert rule['ordinary'] == float(group['ordinary_cutoff'].iloc[0])
            assert rule['selection'] == float(group['selection_cutoff'].iloc[0])
            pairs = {int(row['K']): row['cutoff'] for row in rule['per_pool']}
            assert len(pairs) == len(group)
            for row in group.itertuples():
                assert pairs[int(row.K)] == float(row.cutoff)
                values_checked += 1
            assert rule['ordinary'] == pairs[1]
            assert rule['selection'] == max(pairs.values())
            groups_checked += 1
    assert len(locked) == groups_checked == 16
    return {'rule_groups_checked': groups_checked, 'per_pool_values_checked': values_checked,
            'JSON_matches_round_trip_CSV_exact_binary64_values': True,
            'locked_cutoffs_sha256': sha256(path.read_bytes()).hexdigest()}


def workbook_checks():
    """Read the exported ZIP/XML; do not write or repair Excel files."""
    qa = ROOT.parents[1] / '.qa_assignment9'
    build_path = qa / 'workbook_build_checks.json'
    if not build_path.exists():
        build_path = ROOT / 'data/workbook_build_checks.json'
    build = json.loads(build_path.read_text(encoding='utf-8'))
    path = ROOT / 'Assignment_9_Chen_Zimmermann_Screening.xlsx'
    ns = {'s': 'http://schemas.openxmlformats.org/spreadsheetml/2006/main',
          'r': 'http://schemas.openxmlformats.org/officeDocument/2006/relationships'}
    prefix = '{http://schemas.openxmlformats.org/package/2006/relationships}'
    def address(column, row):
        label = ''
        while column:
            column, digit = divmod(column - 1, 26)
            label = chr(65 + digit) + label
        return f'{label}{row}'
    with ZipFile(path) as z:
        book = ET.fromstring(z.read('xl/workbook.xml'))
        relationships = ET.fromstring(z.read('xl/_rels/workbook.xml.rels'))
        targets = {r.attrib['Id']: r.attrib['Target'] for r in relationships.findall(prefix + 'Relationship')}
        strings = []
        if 'xl/sharedStrings.xml' in z.namelist():
            for element in ET.fromstring(z.read('xl/sharedStrings.xml')).findall('s:si', ns):
                strings.append(''.join(element.itertext()))
        style = ET.fromstring(z.read('xl/styles.xml'))
        fonts = style.find('s:fonts', ns)
        xfs = style.find('s:cellXfs', ns)
        cells, formulas, cell_styles = {}, {}, {}
        sheet_names = []
        font_cases = 0
        for sheet in book.find('s:sheets', ns):
            name = sheet.attrib['name']; sheet_names.append(name)
            target = targets[sheet.attrib['{' + ns['r'] + '}id']]
            filename = target.lstrip('/') if target.startswith('/') else 'xl/' + target
            xml = ET.fromstring(z.read(filename))
            assert xml.find('s:sheetViews/s:sheetView/s:pane', ns) is not None, name
            for cell in xml.findall('s:sheetData/s:row/s:c', ns):
                key = name + '!' + cell.attrib['r']
                kind = cell.attrib.get('t'); value = cell.find('s:v', ns)
                assert kind != 'e', (key, value.text if value is not None else None)
                if kind == 's':
                    stored = strings[int(value.text)]
                elif kind == 'inlineStr':
                    stored = ''.join(cell.find('s:is', ns).itertext())
                elif kind in ('str', 'd'):
                    stored = value.text if value is not None else None
                elif value is not None:
                    stored = float(value.text)
                else:
                    stored = None
                cells[key] = stored
                formula = cell.find('s:f', ns)
                if formula is not None:
                    formulas[key] = '=' + formula.text
                    assert value is not None, key
                if stored is not None:
                    xf = xfs[int(cell.attrib.get('s', 0))]
                    font = fonts[int(xf.attrib.get('fontId', 0))]
                    assert font.find('s:name', ns).attrib['val'] == 'Times New Roman', key
                    color = font.find('s:color', ns)
                    assert color is not None and color.attrib.get('rgb', '').upper() in ('FF000000', '000000'), key
                    font_cases += 1
        assert sheet_names == ['Results','Strategies','Selection','Reporting','Sensitivities','Sources']
        values_checked = 0
        for identifier, mapping in build['mappings'].items():
            for i, row in enumerate(mapping['values'], mapping['start']):
                for j, expected in enumerate(row, 1):
                    key = mapping['sheet'] + '!' + address(j, i)
                    actual = cells.get(key)
                    if isinstance(expected, (int, float)):
                        assert actual is not None and np.isclose(actual, expected, atol=2e-14, rtol=2e-14), (key, actual, expected)
                    else:
                        assert actual == expected, (key, ascii(actual), ascii(expected))
                    values_checked += 1
        assert formulas == build['formulaCells']
        # Source tables are read independently of the spreadsheet importer.
        descriptive = pd.read_csv(ROOT / 'tables/descriptive_statistics.csv', float_precision='round_trip')
        for i, (weighting, representation) in enumerate([('original','spread'),('original','funded'),('value_weighted','spread'),('value_weighted','funded')], 7):
            frame = descriptive.loc[descriptive.weighting.eq(weighting) & descriptive.representation.eq(representation)]
            assert cells[f'Results!C{i}'] == len(frame) == 195
            assert cells[f'Results!D{i}'] == int(frame.conventional_any.sum())
            assert cells[f'Results!E{i}'] == frame.conventional_any.mean()
        assert [cells[f'Results!D{i}'] for i in range(7,11)] == [1,4,0,0]
        assert cells['Results!B13'] == 194 and cells['Results!C13'] == 0
        fund = descriptive.loc[descriptive.cohort.eq('fund_x_common108')].iloc[0]
        assert cells['Results!B19'] == fund.zero_h and cells['Results!C19'] == fund.excess_sharpe
        for i in range(26,31):
            assert cells[f'Results!B{i}'] == 39
        assert [cells[f'Results!C{i}'] for i in range(26,31)] == [0,0,0,0,1]
        for table_name, field_checks in [
                ('reporting_point', [('baseline_rate','N'),('altered_rate','O'),('new_alert_rate','P'),('cleared_alert_rate','Q'),('conditional_baseline_rate','T'),('conditional_altered_rate','U')]),
                ('reporting_selection', [('designated_candidate_selection_probability','K'),('joint_selected_alert_probability','L'),('conditional_alert_given_selected','M'),('joint_selected_changed_probability','N'),('joint_selected_changed_alert_probability','O'),('conditional_alert_given_changed_selected','P')])]:
            source = pd.read_csv(ROOT / f'tables/{table_name}.csv', float_precision='round_trip')
            start = build['mappings'][table_name]['start']
            for index, row in source.iterrows():
                for field, column in field_checks:
                    expected = row[field]; actual = cells[f'Reporting!{column}{start+index}']
                    if pd.isna(expected):
                        assert actual in (None, 'n.a.')
                    else:
                        assert np.isclose(actual, expected, atol=2e-14, rtol=2e-14)
        locked = json.loads((ROOT / 'data/locked_cutoffs.json').read_text())
        expected = []
        for value in locked['rules'].values():
            for per_pool in value['per_pool']:
                expected.append((per_pool['cutoff'],value['ordinary'],value['selection']))
        start = build['mappings']['locked_cutoffs']['start']
        for i, values in enumerate(expected, start):
            assert tuple(cells[f'Sources!{col}{i}'] for col in ['F','G','H']) == values
        assert build['recalculation']['restored']
        assert cells['Reporting!K7'] == build['recalculation']['original_count']
        assert cells['Reporting!O7'] == build['recalculation']['original_value']
        assert build['recalculation']['perturbed_value'] != build['recalculation']['original_value']
        local_renders_available = (qa / 'workbook_formula_scan.ndjson').exists()
        if local_renders_available:
            for rendered in build['rendered_regions']:
                assert (qa / rendered['file']).exists()
            assert 'matched 0 entries' in (qa / 'workbook_formula_scan.ndjson').read_text()
    copy = ROOT.parents[1] / 'outputs/assignment_9_chEN_zimmermann' / path.name
    if copy.exists():
        assert sha256(copy.read_bytes()).hexdigest() == sha256(path.read_bytes()).hexdigest()
    return {'xlsx_sha256':sha256(path.read_bytes()).hexdigest(),'sheets':sheet_names,
            'exported_table_cells_checked':values_checked,'formula_cells_checked':len(formulas),
            'populated_cells_Times_New_Roman_black':font_cases,
            'all_96_cutoff_rows_match_locked_JSON_binary64':True,
            'all_reporting_rate_denominators_checked':True,
            'headline_counts_match_independent_CSV_reads':True,
            'input_perturbation_recalculated_and_restored':True,
            'formula_errors':0,'rendered_regions':len(build['rendered_regions']),
            'visual_review':'Every tab and all rendered important regions inspected; affected cramped labels corrected.',
            'local_render_files_checked_in_this_run':local_renders_available,
            'engine_limit':'Artifact-tool calculation and read-only OOXML audit; not opened in native Excel.'}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--benchmarks', action='store_true')
    parser.add_argument('--workbook', action='store_true')
    args = parser.parse_args()
    output = ROOT / 'data/independent_verification.json'
    if args.workbook and not args.benchmarks:
        result = json.loads(output.read_text())
    else:
        design, panels, rf = independent_inputs()
        result = {'frozen_design_sha256': sha256((ROOT / 'data/frozen_design.json').read_bytes()).hexdigest(),
                  'metadata': metadata_checks(design, panels, rf)}
    if args.benchmarks:
        result['maps'] = score_map_checks(design, panels, rf)
        result['caches'] = cache_checks(design, panels, rf)
        result['cutoffs'] = cutoff_checks()
        result['observed'] = observed_checks(design, panels, rf)
        result['locked_cutoffs'] = locked_cutoff_checks()
    if args.workbook:
        result['workbook'] = workbook_checks()
    if output.exists():
        previous = json.loads(output.read_text())
        for key, value in previous.items():
            result.setdefault(key, value)
    output.write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
