"""Freeze the public portfolio-level data used in Assignment 9."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from hashlib import sha256
from io import BytesIO
from pathlib import Path
from urllib.parse import quote
from zipfile import ZipFile
import json
import shutil

import pandas as pd
import requests

ROOT = Path(__file__).resolve().parents[1]
COMMIT = 'dd1054254c4501776432caa6d7ce5ecd9586f6a9'
FILES = {
    'PredictorLSretWide.parquet': ('Portfolios/Full Sets OP/PredictorLSretWide.parquet',
        'fc01df25d4383153cb3ae9e0dd730cc34b6d15a5207abeff09f34beda45bca58'),
    'PredictorPortsFull.parquet': ('Portfolios/Full Sets OP/PredictorPortsFull.parquet',
        '76599d94beab94cc8973d8a126e8efbed98ee79f677738c55b2389f17387ba96'),
    'PredictorVWforce.parquet': ('Portfolios/Full Sets Alt/PredictorAltPorts_LiqScreen_VWforce.parquet',
        'e64df0fc189f1a4f4ce3ba39fdbba2ee83dfce871c6bf60f5660cbc9222158db'),
    'SignalDoc.csv': ('SignalDoc.csv',
        '0ceb11020c2138c2477b732948beaac2e67ccaad8428753e3a79af2bb5ea0178'),
}


def get_file(item):
    name, (relative, expected) = item
    target = ROOT / 'data' / 'raw' / name
    url = f'https://huggingface.co/datasets/OpenSourceAP/CrossSection/resolve/{COMMIT}/{quote(relative)}'
    if target.exists():
        content = target.read_bytes()
    else:
        response = requests.get(url, timeout=120)
        response.raise_for_status()
        content = response.content
    actual = sha256(content).hexdigest()
    if actual != expected:
        raise ValueError(f'Unexpected source hash for {name}')
    target.write_bytes(content)
    return dict(file=f'data/raw/{name}', source_url=url, sha256=actual, bytes=len(content))


def main():
    (ROOT / 'data' / 'raw').mkdir(parents=True, exist_ok=True)
    with ThreadPoolExecutor(max_workers=4) as executor:
        sources = list(executor.map(get_file, FILES.items()))
    french = ROOT / 'data/raw/F-F_Research_Data_Factors_CSV.zip'
    url = 'https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/ftp/F-F_Research_Data_Factors_CSV.zip'
    if not french.exists():
        response = requests.get(url, timeout=60)
        response.raise_for_status()
        french.write_bytes(response.content)
    with ZipFile(BytesIO(french.read_bytes())) as archive:
        names = [name for name in archive.namelist() if name.lower().endswith('.csv')]
        if len(names) != 1:
            raise ValueError('Expected one French monthly/annual CSV')
        (ROOT / 'data/raw/F-F_Research_Data_Factors.csv').write_bytes(archive.read(names[0]))
    sources.append(dict(file=str(french.relative_to(ROOT)).replace('\\', '/'), source_url=url,
                        sha256=sha256(french.read_bytes()).hexdigest(), bytes=french.stat().st_size))
    old = ROOT.parent / 'assignment_8/data/fund_x_2017_01_to_2026_09.csv'
    frozen = ROOT / 'data/raw/fund_x_2017_01_to_2026_09.csv'
    if not frozen.exists():
        shutil.copy2(old, frozen)
    expected_fund_x = 'd869d0f0721d63c4e9c89336b82415c2b283f6a8701b7e71838e8432b7e2bc45'
    if sha256(frozen.read_bytes()).hexdigest() != expected_fund_x:
        raise ValueError('Frozen Fund X file differs from the checked paper series')
    sources.append(dict(file=str(frozen.relative_to(ROOT)).replace('\\', '/'),
                        source='Assignment 8 frozen published I-series net USD returns, independently matched to current paper',
                        sha256=sha256(frozen.read_bytes()).hexdigest()))
    meta = dict(downloaded_utc=datetime.now(timezone.utc).isoformat(),
                release='2026.10', dataset_commit=COMMIT, license='CC BY 4.0 for CZ published portfolio data',
                creator='Andrew Y. Chen and Tom Zimmermann',
                paper='Open Source Cross-Sectional Asset Pricing (2022), Critical Finance Review 11(2),207–264',
                sources=sources)
    (ROOT / 'data/source_provenance.json').write_text(json.dumps(meta, indent=2)+'\n', encoding='utf-8')
    wide = pd.read_parquet(ROOT / 'data/raw/PredictorLSretWide.parquet')
    dates = pd.to_datetime(wide['date']).dt.to_period('M')
    coverage = []
    periods = [('development', '1980-01', '2004-12'),
               ('calibration', '2005-01', '2016-12'),
               ('evaluation', '2017-01', '2025-12')]
    for name, start, end in periods:
        panel = wide.loc[(dates >= start) & (dates <= end)].drop(columns='date')
        coverage.append(dict(period=name, months=len(panel), complete_signals=int(panel.notna().all().sum())))
    doc = pd.read_csv(ROOT / 'data/raw/SignalDoc.csv')
    print(json.dumps(dict(status='frozen inputs downloaded', shape=list(wide.shape),
                         earliest=str(dates.min()), latest=str(dates.max()), coverage=coverage,
                         documentation_columns=list(doc.columns)), indent=2))


if __name__ == '__main__':
    main()
