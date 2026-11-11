"""Copy checked deliverables to University and inventory this analysis release."""
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
import importlib.metadata
import json
import shutil

import fitz
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
STEM = 'Assignment_9_Chen_Zimmermann_Screening'
UNIVERSITY = Path('C:/Users/HP/Desktop/University/Working Manuscripts/Active Papers/Fund X Paper Review/Research/Assignment 9')


def digest(path):
    return sha256(path.read_bytes()).hexdigest()


def copy_checked(source, destination):
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists() and digest(source) != digest(destination):
        history = UNIVERSITY / 'History' / (destination.stem+'_'+digest(destination)[:12]+destination.suffix)
        history.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(destination, history)
    shutil.copy2(source, destination)
    assert digest(source) == digest(destination)
    return dict(file=str(destination), sha256=digest(destination))


def main():
    pdf = ROOT / f'{STEM}.pdf'
    doc = fitz.open(pdf)
    assert len(doc) == 6
    for i, page in enumerate(doc):
        assert '11 November 2026' in page.get_text(), i
        assert (ROOT / '.qa_assignment9/report' / f'page_{i+1}.png').exists()
    log = (ROOT / f'{STEM}.log').read_text(encoding='utf-8')
    assert 'Overfull' not in log and 'Missing character' not in log
    evidence = json.loads((ROOT / 'data/independent_verification.json').read_text())
    reporting = pd.read_csv(ROOT / 'tables/reporting_point.csv', float_precision='round_trip')
    primary = reporting[(reporting.months == 108) & (reporting.weighting == 'original') & (reporting.representation == 'spread') & (reporting.delta == .01) & (reporting.probability == 1) & (reporting.lag.astype(str) == '3')]
    assert primary.changed_paths.eq(194).all()
    counts = {row.method: int(row.altered_alerts) for row in primary.itertuples()}
    assert [counts[m] for m in ['conventional_any', 'ordinary_calibrated', 'selection_calibrated']] == [120, 111, 66]
    outputs = []
    for suffix in ['pdf', 'tex', 'xlsx']:
        outputs.append(copy_checked(ROOT / f'{STEM}.{suffix}', UNIVERSITY / f'{STEM}.{suffix}'))
    for figure in sorted((ROOT / 'figures').glob('*.png')):
        copy_checked(figure, UNIVERSITY / 'figures' / figure.name)
    output_dir = ROOT.parents[1] / 'outputs/assignment_9_chEN_zimmermann'
    for suffix in ['pdf', 'tex', 'xlsx']:
        copy_checked(ROOT / f'{STEM}.{suffix}', output_dir / f'{STEM}.{suffix}')
    pointer = ('Assignment 9: Chen–Zimmermann return-screening results, 11 November 2026.\n'
               'Read the PDF for findings; the workbook contains the supporting calculations.\n'
               'The matching TeX source uses the figures subfolder.\n'
               'Reproducible analysis: C:/Users/HP/Prof Boyle/codex_project1a_context/'
               'project1_may2026_deliverables/workspace/assignment_9/README.md\n')
    (UNIVERSITY / 'Current_version.txt').write_text(pointer, encoding='utf-8')
    included = []
    for folder in ['scripts', 'tables', 'figures', 'data']:
        for path in sorted((ROOT / folder).rglob('*')):
            if not path.is_file() or any(part in ['__pycache__', 'score_cache'] for part in path.relative_to(ROOT).parts):
                continue
            included.append(dict(file=path.relative_to(ROOT).as_posix(), bytes=path.stat().st_size, sha256=digest(path)))
    for name in [f'{STEM}.pdf', f'{STEM}.tex', f'{STEM}.xlsx', 'README.md', '.gitignore', '.gitattributes']:
        path = ROOT / name
        included.append(dict(file=name, bytes=path.stat().st_size, sha256=digest(path)))
    versions = {name: importlib.metadata.version(name) for name in ['numpy', 'pandas', 'scipy', 'statsmodels', 'pyarrow', 'matplotlib', 'requests', 'PyMuPDF']}
    publication = dict(status='prepared local release; no remote publication claimed until separately verified')
    if (ROOT / 'data/publication_readback.json').exists():
        publication = dict(status='published and raw Drive readback verified',
                           **json.loads((ROOT / 'data/publication_readback.json').read_text()))
    manifest = dict(
        assignment=9, release_date='2026-11-11', finalized_utc=datetime.now(timezone.utc).isoformat(),
        scope='Chen–Zimmermann portfolios; historical selection, calibration, paired reporting changes and exploratory fixed-weight combinations',
        paper_input='Outer main.tex in supplied Curious_CaseX(5).zip; nested older paper retained only as historical input',
        private_original_inputs='Preserved locally under source/ and excluded from the public GitHub repository',
        source_provenance='data/source_provenance.json',
        pinned_dataset_commit='dd1054254c4501776432caa6d7ce5ecd9586f6a9',
        common_window=['2017-01', '2025-12'], months=108, published_factor_count=212,
        descriptive_complete_strategies=195, common_calibration_evaluation_core=194,
        development=['1980-01','2004-12'], calibration=['2005-01','2016-12'],
        frozen_design_sha256=digest(ROOT / 'data/frozen_design.json'),
        exact_cutoffs_sha256=digest(ROOT / 'data/locked_cutoffs.json'),
        exploratory_timing='Separately frozen after individual-factor support gap found and before combination outcomes evaluated',
        primary_unmodified_conventional_counts=dict(original_spread=1, original_funded=4, value_weighted_spread=0, value_weighted_funded=0),
        primary_reporting=dict(loss_bound=.01, initial_gain=.0005, hiding_probability=1, recognition_lag_months=3,
                               denominator=194, changed_paths=194, altered_warning_counts=counts,
                               conventional_new_warnings=119, selection_new_warnings=66),
        limits=['Constructed strategy returns, not live fund NAVs', 'Gross source portfolios versus reported net Fund X',
                'No real-fund honesty or fraud labels', 'Individual factors do not reach Fund X performance range',
                'Exploratory funded combination approaches zero-rate ratio but not Fund X mean or excess Sharpe',
                '5% calibration target is not a later-data guarantee; held-out full-pool value-spread60 block12 frequency9.4%',
                'Conditional block and policy uncertainty, overlapping factors and windows',
                'Measured empirical comparison; substantial new statistical method not established'],
        validation=evidence,
        report_check=dict(pages=6, every_page_rendered_and_visually_inspected=True, overfull_boxes=0, missing_characters=0,
                          cold_read_complete=True, corrections_applied=['changed paths194','held-out cohort terminology','value-spread block12 sensitivity scope','119 newly triggered conventional warnings','closest bias-ratio application']),
        numerical_execution=dict(location='local Windows CPU', principal_runs_seconds=[66.2,71.9,87.5],
                                 cpu26_used=False, reason='Each numerical job completed well below ten minutes'),
        environment=versions, university_copies=outputs,
        publication=publication,
        files=included,
    )
    target = ROOT / 'assignment9_manifest.json'
    target.write_text(json.dumps(manifest, indent=2, ensure_ascii=False)+'\n', encoding='utf-8')
    print(json.dumps(dict(manifest=str(target), inventoried_files=len(included), university_copies=outputs),indent=2))


if __name__ == '__main__':
    main()
