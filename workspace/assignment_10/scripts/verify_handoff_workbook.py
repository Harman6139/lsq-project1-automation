"""Read-only saved-XLSX reconciliation; no spreadsheet authoring libraries."""
import csv
import hashlib
import json
import math
import pathlib
import re
import xml.etree.ElementTree as ET
import zipfile

ROOT = pathlib.Path(__file__).resolve().parents[1]
QA = ROOT.parents[1] / '.qa_assignment10'
FILE = ROOT / 'Assignment_10_Return_Screening_Frontier_Handoff.xlsx'
NS = {'s': 'http://schemas.openxmlformats.org/spreadsheetml/2006/main',
      'c': 'http://schemas.openxmlformats.org/drawingml/2006/chart'}

def source(name):
    with (ROOT / 'tables' / name).open(newline='', encoding='utf-8-sig') as f:
        return list(csv.DictReader(f))

def column(n):
    out = ''
    while n:
        n, k = divmod(n-1, 26)
        out = chr(65+k) + out
    return out

def equal(actual, expected, label):
    if isinstance(expected, bool):
        assert actual == int(expected), (label, actual, expected)
    elif isinstance(expected, (float, int)):
        assert isinstance(actual, (float, int)) and math.isclose(actual, expected, abs_tol=1e-12, rel_tol=1e-12), (label, actual, expected)
    else:
        assert actual == expected or (expected is None and actual == ''), (label, actual, expected)

def main():
    build = json.loads((QA / 'workbook_build_checks.json').read_text(encoding='utf-8'))
    mapping = json.loads((QA / 'workbook_cell_map.json').read_text(encoding='utf-8'))
    digest = hashlib.sha256(FILE.read_bytes()).hexdigest()
    assert digest == build['sha256']
    with zipfile.ZipFile(FILE) as z:
        strings = []
        if 'xl/sharedStrings.xml' in z.namelist():
            strings = [''.join(x.itertext()) for x in ET.fromstring(z.read('xl/sharedStrings.xml'))]
        workbook = ET.fromstring(z.read('xl/workbook.xml'))
        names = [x.attrib['name'] for x in workbook.find('s:sheets', NS)]
        assert names == ['Comparison', 'Frontiers', 'Other histories', 'Sources'], names
        sheet_data = {}
        style_ids = set()
        formula_count = 0
        for i, name in enumerate(names, 1):
            tree = ET.fromstring(z.read(f'xl/worksheets/sheet{i}.xml'))
            data = {}
            assert tree.find('s:mergeCells', NS) is None, name
            for c in tree.findall('.//s:sheetData/s:row/s:c', NS):
                v = c.find('s:v', NS)
                t = c.attrib.get('t', '')
                f = c.find('s:f', NS)
                if t == 's':
                    value = strings[int(v.text)]
                elif t == 'inlineStr':
                    value = ''.join(c.find('s:is', NS).itertext())
                elif t == 'str':
                    value = v.text if v is not None else None
                else:
                    value = float(v.text) if v is not None and v.text is not None else None
                assert t != 'e', (name, c.attrib['r'], value)
                if value is not None:
                    style_ids.add(int(c.attrib.get('s', 0)))
                data[c.attrib['r']] = (value, f.text if f is not None else None)
                formula_count += f is not None
            sheet_data[name] = data
        def cell(sheet, address):
            return sheet_data[sheet].get(address, (None, None))[0]
        mapped_cells = 0
        checked_formulas = 0
        for key, m in mapping.items():
            for i, values in enumerate(m['saved_values'], m['start']):
                for j, expected in enumerate(values, 1):
                    address = f'{column(j)}{i}'
                    equal(cell(m['sheet'], address), expected, (key, address))
                    mapped_cells += 1
                    formula = m['formulas'][i-m['start']][j-1]
                    if formula:
                        saved = sheet_data[m['sheet']][address][1]
                        assert saved == formula.lstrip('='), (key, address, saved, formula)
                        match = re.fullmatch(r'=([A-Z]+\d+)/([A-Z]+\d+)', formula)
                        assert match, formula
                        equal(cell(m['sheet'], address), cell(m['sheet'], match[1])/cell(m['sheet'], match[2]), (key, address, 'independent ratio'))
                        checked_formulas += 1
        assert checked_formulas == formula_count, (checked_formulas, formula_count)

        # Independent comparisons to original analysis CSVs, not the authoring cell map.
        source_count_cells = 0
        for i, r in enumerate(source('handoff_comparison.csv'), 15):
            for c, k in [('C','n'),('D','old_pair_warnings'),('F','local_serial_pair_warnings'),('H','old_pair_baseline'),('I','local_serial_pair_baseline'),('J','old_pair_new'),('K','local_serial_pair_new')]:
                equal(cell('Comparison', f'{c}{i}'), int(r[k]), ('main CSV',i,k)); source_count_cells += 1
        for i,r in enumerate(source('naive_results.csv'),8):
            for c,k in [('B','n'),('C','unchanged_warnings'),('E','altered_warnings'),('G','new_warnings')]:
                equal(cell('Comparison',f'{c}{i}'),int(r[k]),('starting CSV',i,k)); source_count_cells += 1
        pids = ['B','D','A','Z','OR:B+D','OR:A+Z','OR:B+A+Z','OR:B+D+A+Z']
        mechs = ['relative_permanent','relative_delay3','fixed_delay3','smooth50']
        rows = [r for r in source('frontier_curves_original.csv') if r['group']=='all' and float(r['budget'])<=.20 and r['policy'] in pids and r['mechanism'] in mechs]
        rows.sort(key=lambda r:(mechs.index(r['mechanism']),pids.index(r['policy']),float(r['budget'])))
        assert len(rows)==672
        for i,r in enumerate(rows,33):
            for c,k in [('C','budget'),('D','n'),('E','baseline'),('G','altered'),('I','new'),('J','changed')]:
                equal(cell('Frontiers',f'{c}{i}'),float(r[k]),('frontier CSV',i,k)); source_count_cells += 1
        external_pids = ['OR:B+D','OR:A+Z','OR:B+A+Z','OR:B+D+A+Z']
        external_mechs = ['unmodified','relative_permanent','relative_delay3','relative_half_delay3','smooth50']
        erows = [r for r in source('external_rates.csv') if float(r['budget'])==.05 and r['policy'] in external_pids and r['mechanism'] in external_mechs and ((r['source']=='CPZ_author' and r['group']=='SDF') or (r['source']=='JKP_world' and r['group']=='all') or (r['source']=='public_NAV' and r['group']!='all') or (r['source']=='Fund_X' and r['group']=='case_only'))]
        erows.sort(key=lambda r:(f"{r['source']}|{r['sample']}|{r['group']}|{r['policy']}",external_mechs.index(r['mechanism'])))
        assert len(erows)==164
        for i,r in enumerate(erows,34):
            for c,k in [('E','n'),('F','changed'),('G','baseline'),('I','altered'),('K','new')]:
                equal(cell('Other histories',f'{c}{i}'),int(r[k]),('external CSV',i,k)); source_count_cells += 1
        # All available selected-rule cases, including zero-eligible-change cases, remain present.
        zero_changed = sum(r['mechanism']!='unmodified' and int(r['changed'])==0 for r in erows)
        styles = ET.fromstring(z.read('xl/styles.xml'))
        fonts = styles.find('s:fonts', NS)
        xfs = styles.find('s:cellXfs', NS)
        for sid in style_ids:
            f = fonts[int(xfs[sid].attrib['fontId'])]
            assert f.find('s:name', NS).attrib['val'] == 'Times New Roman', sid
            rgb = f.find('s:color', NS).attrib.get('rgb')
            assert rgb in ['FF000000','00000000','000000'], (sid,rgb)
        charts = sorted(n for n in z.namelist() if re.fullmatch(r'xl/(?:drawings/)?charts/chart\d+\.xml',n))
        assert not charts, charts
        media=[n for n in z.namelist() if n.startswith('xl/media/')]
        assert len(media)==1,media
        embedded_hash=hashlib.sha256(z.read(media[0])).hexdigest()
        assert embedded_hash==build['figure']['sha256']
        assert embedded_hash==hashlib.sha256(pathlib.Path(build['figure']['path']).read_bytes()).hexdigest()
        assert not any('externalLink' in n for n in z.namelist())
    copy = ROOT/'outputs/assignment10_handoff_20261119'/FILE.name
    assert hashlib.sha256(copy.read_bytes()).hexdigest()==digest
    evidence = dict(status='passed',file=str(FILE),sha256=digest,worksheets=names,
                    mapped_saved_cells=mapped_cells,source_count_cells=source_count_cells,
                    independently_recalculated_ratios=checked_formulas,formula_errors=0,
                    scientific_figure=dict(build['figure'],embedded_path=media[0],embedded_bytes_match=True),all_used_cell_fonts='Times New Roman, black',
                    selected_external_rows=164,zero_changed_altered_cases_retained=zero_changed,
                    count_perturbation_and_restoration=build['formulaChecks'],
                    renders=build['renderRegions'],authoring_event=build['authoring_event'],
                    rendering_review='All 16 regions inspected; revised labels, alignment and return-basis column rechecked.',
                    limitation='Native Excel application was not opened. Recalculation was checked in the bundled engine and saved OOXML was independently reconciled. The approved fixed scientific figure is embedded because both documented native-scatter routes exported empty point sources in this runtime. All 672 frontier rows remain in the visible formula-backed table.')
    (ROOT/'data/workbook_verification.json').write_text(json.dumps(evidence,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({k:v for k,v in evidence.items() if k not in ['renders','count_perturbation_and_restoration','authoring_event']},indent=2))

if __name__=='__main__':
    main()
