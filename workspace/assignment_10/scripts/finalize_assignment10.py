"""Check the compact handoff, copy it to University, and inventory the release."""
from datetime import datetime,timezone
from hashlib import sha256
from pathlib import Path
import json
import shutil

import fitz
import numpy as np
import pandas as pd

from frontier_engine import dependency_hashes

ROOT=Path(__file__).resolve().parents[1]
STEM='Return_Screening_Frontier'
BOOK_STEM='Assignment_10_Return_Screening_Frontier_Handoff'
UNIVERSITY=Path('C:/Users/HP/Desktop/University/Working Manuscripts/Active Papers/Fund X Paper Review/Research/Assignment 10')


def digest(path): return sha256(path.read_bytes()).hexdigest()


def copy_checked(source,destination):
    destination.parent.mkdir(parents=True,exist_ok=True)
    if destination.exists() and digest(source)!=digest(destination):
        history=UNIVERSITY/'History'/(destination.stem+'_'+digest(destination)[:12]+destination.suffix)
        history.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(destination,history)
        inventory=UNIVERSITY/'History/original_paths.json'
        records=json.loads(inventory.read_text()) if inventory.exists() else []
        records.append(dict(original_path=str(destination),preserved_path=str(history),sha256=digest(history)))
        inventory.write_text(json.dumps(records,indent=2)+'\n')
    shutil.copy2(source,destination);assert digest(source)==digest(destination)
    return dict(file=str(destination),sha256=digest(destination))


def main():
    document=fitz.open(ROOT/f'{STEM}.pdf')
    assert 2<=len(document)<=3
    words=sum(len(page.get_text().split()) for page in document)
    graph=fitz.open(ROOT/'figures/Return_Screening_Frontier_Explained.pdf')
    assert len(graph)==1
    assert (ROOT/'.qa_assignment10/methods/frontier_standalone.png').exists()
    log=(ROOT/f'{STEM}.log').read_text()
    assert 'Overfull' not in log and 'Missing character' not in log
    assert all((ROOT/f'.qa_assignment10/conversational_20261120/page_{n}.png').exists() for n in range(1,len(document)+1))
    email=ROOT/'Email_to_Professor_Boyle_Frontier_Handoff.txt'
    assert 200<=len(email.read_text().split())<=250
    verification=json.loads((ROOT/'data/independent_verification.json').read_text())
    assert verification['scalar_checks']['status']=='passed'
    bookcheck=json.loads((ROOT/'data/workbook_verification.json').read_text())
    assert bookcheck['status']=='passed' and bookcheck['formula_errors']==0
    assert digest(ROOT/f'{BOOK_STEM}.xlsx')==bookcheck['sha256']
    checked_rows=0
    for name in ['point_rates_original','point_rates_value_weighted','external_rates']:
        data=pd.read_csv(ROOT/f'tables/{name}.csv',float_precision='round_trip')
        assert (data.n>0).all()
        assert (data.altered-data.baseline==data.new-data.cleared).all()
        for field in ['baseline','altered','new','cleared','changed']:
            assert (data[field]>=0).all() and (data[field]<=data.n).all()
        for count,rate in [('baseline','baseline_rate'),('altered','altered_rate'),('new','new_rate')]:
            assert np.allclose(data[count]/data.n,data[rate],rtol=0,atol=2e-15)
        checked_rows+=len(data)
    for record in json.loads((ROOT/'data/source_provenance.json').read_text())['sources']:
        assert digest(ROOT/record['file'])==record['sha256']
    for record in json.loads((ROOT/'data/external_validation_inputs.json').read_text())['files']:
        assert digest(ROOT/record['file'])==record['sha256']
    executions={p.stem:json.loads(p.read_text()) for p in sorted((ROOT/'data').glob('execution_*.json'))}
    current=dependency_hashes()
    for record in executions.values():
        assert record['status']=='complete' and record['dependencies']==current
    cache_checks=0
    for path in sorted((ROOT/'data/cache').glob('*.json')):
        metadata=json.loads(path.read_text());assert metadata['settings']['dependencies']==current
        with np.load(path.with_suffix('.npz')) as saved:
            assert np.all(saved['calibration_rates']<=np.linspace(0,1,101)[None,:]+1e-12)
        cache_checks+=1
    copies=[]
    for ext in ['pdf','tex']:
        copies.append(copy_checked(ROOT/f'{STEM}.{ext}',UNIVERSITY/f'{STEM}.{ext}'))
        copy_checked(ROOT/f'{STEM}.{ext}',ROOT.parents[1]/'outputs/assignment10_handoff_20261119'/f'{STEM}.{ext}')
    copies.append(copy_checked(ROOT/f'{BOOK_STEM}.xlsx',UNIVERSITY/f'{BOOK_STEM}.xlsx'))
    for figure in ['report_loss_delay.png','report_smoothing.png']:
        copies.append(copy_checked(ROOT/'figures'/figure,UNIVERSITY/'figures'/figure))
    for ext in ['png','svg']:
        figure=f'conversational_frontier.{ext}'
        copies.append(copy_checked(ROOT/'figures'/figure,UNIVERSITY/'figures'/figure))
    for ext in ['png','svg','pdf']:
        figure=f'Return_Screening_Frontier_Explained.{ext}'
        copies.append(copy_checked(ROOT/'figures'/figure,UNIVERSITY/'figures'/figure))
    copies.append(copy_checked(email,UNIVERSITY/email.name))
    (UNIVERSITY/'Current_version.txt').write_text(
        f'Return screening: the experiment and its results, 20 November 2026.\nCurrent report: Return_Screening_Frontier.pdf (three pages), with matching LaTeX and one count-axis graph. The standalone frontier graph is under figures/, in PDF, PNG and SVG formats. The supporting workbook is unchanged. The current unsent email draft has {len(email.read_text().split())} words.\nThe prior one-page note is preserved in History/20261119_One_Page_Handoff; superseded three-page versions are preserved by hash under History.\n'
        'Sources and reproduction: C:/Users/HP/Prof Boyle/codex_project1a_context/project1_may2026_deliverables/workspace/assignment_10/README.md\n',encoding='utf-8')
    files=[]
    for folder in ['scripts','data','tables','figures','research','History']:
        for path in sorted((ROOT/folder).rglob('*')):
            if not path.is_file(): continue
            rel=path.relative_to(ROOT)
            if any(p in ['cache','external','__pycache__'] for p in rel.parts):continue
            if path.name in ['download_inventory.json','build_email_draft.py'] or '.private.' in path.name:continue
            files.append(dict(file=rel.as_posix(),bytes=path.stat().st_size,sha256=digest(path)))
    for name in [f'{STEM}.pdf',f'{STEM}.tex',f'{BOOK_STEM}.xlsx','README.md','.gitignore','.gitattributes']:
        path=ROOT/name;files.append(dict(file=name,bytes=path.stat().st_size,sha256=digest(path)))
    publication=dict(status='prepared local release; remote publication not yet claimed')
    if (ROOT/'data/publication_readback.json').exists():
        readback=json.loads((ROOT/'data/publication_readback.json').read_text())
        required={digest(ROOT/f'{STEM}.pdf'),digest(ROOT/f'{BOOK_STEM}.xlsx'),digest(ROOT/'figures/Return_Screening_Frontier_Explained.pdf')}
        verified={record['sha256'] for record in readback['files']}
        if required<=verified:
            publication=dict(status='published with byte-for-byte Drive readback',**readback)
    summary=json.loads((ROOT/'data/results_summary.json').read_text())
    manifest=dict(assignment=10,release_date='2026-11-20',finalized_utc=datetime.now(timezone.utc).isoformat(),
        objective='Compare types and quantities of return-warning checks at declared historical warning budgets; test controlled reporting changes in later dates and other histories',
        frozen_design_sha256=digest(ROOT/'data/frozen_design.json'),policies=dict(primary=26,total=38),
        primary_cohort=194,external_world_cohort=153,score_families=['bias ratio','fitted-normal loss deficit','positive serial dependence','local four-bin zero contrast'],
        data_rights='External originals/restricted PDFs, personal Downloads inventory and correspondence stay local and excluded from public Git',
        private_email=dict(file=email.name,sha256=digest(email),words=len(email.read_text().split()),sent=False),
        key_results=summary,verification=verification,workbook_checks=bookcheck,
        full_table_arithmetic_rows_checked=checked_rows,cache_settings_and_budget_checks=cache_checks,
        presentation_revision='Conversational three-page explanation of fund/research counts, ten reporting changes, four checks,38 arrangements,5% target,selected three-check and two-check results, and supported contribution; essential formulas retained; numerical experiments unchanged',
        pdf_checks=dict(pages=len(document),words=words,graphs=1,every_page_rendered_and_visually_inspected=True,overfull_boxes=0,cold_read_complete=True),
        companion_graph_checks=dict(pages=1,annotated_points_verified_against_frozen_source=3,every_page_rendered_and_visually_inspected=True),
        numerical_execution=dict(seconds_by_job={k:v['seconds'] for k,v in executions.items()},
            total_seconds=sum(v['seconds'] for v in executions.values()),cpu26_used=False),
        university_copies=copies,publication=publication,files=files)
    (ROOT/'assignment10_manifest.json').write_text(json.dumps(manifest,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
    print(json.dumps(dict(pdf_words=words,email_words=manifest['private_email']['words'],checked_rows=checked_rows,
                         caches=cache_checks,files=len(files),numerical_seconds=manifest['numerical_execution']['total_seconds'],copies=copies),indent=2))


if __name__=='__main__':main()
