"""Extract public source returns without fitting or evaluating any screen."""
from pathlib import Path
from hashlib import sha256
from math import fsum, sqrt
from statistics import mean, stdev
import csv
import json
import re
import zipfile
import xml.etree.ElementTree as ET

import fitz
import numpy as np
import pandas as pd
import pdfplumber

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / 'data/external'
A9 = ROOT.parent / 'assignment_9'


def monthly_french_cash():
    source = A9 / 'data/raw/F-F_Research_Data_Factors.csv'
    rows = []
    for line in source.read_text(encoding='utf-8-sig').splitlines():
        tokens = [value.strip() for value in line.split(',')]
        if len(tokens) == 5 and re.fullmatch(r'\d{6}', tokens[0]):
            rows.append((tokens[0][:4]+'-'+tokens[0][4:], float(tokens[4])/100))
    data = dict(rows)
    assert len(data) == len(rows)
    return data, source


def extract_pdf(spec, years=range(2017,2026)):
    file, page_index, bounds, year_x, monthly_x, bounds_y = spec
    page = fitz.open(RAW / file)[page_index]
    words = page.get_text('words')
    selected = []
    checks = []
    with pdfplumber.open(RAW / file) as independent:
        text = independent.pages[page_index].crop(bounds).extract_text()
    by_line = {}
    for line in text.splitlines():
        tokens = line.split()
        if tokens and re.fullmatch(r'20\d{2}', tokens[0]):
            year = int(tokens[0])
            if year in years:
                numbers = [float(token.rstrip('%')) for token in tokens[1:]]
                assert len(numbers) == 13, (file, line)
                by_line[year] = numbers
    for year in years:
        anchors = [w for w in words if w[4] == str(year) and w[0] < year_x
                   and bounds_y[0] < (w[1]+w[3])/2 < bounds_y[1]]
        assert len(anchors) == 1, (file, year, anchors)
        y = (anchors[0][1]+anchors[0][3])/2
        row = sorted([w for w in words if abs((w[1]+w[3])/2-y) < 1.7
                      and monthly_x[0] < w[0] < monthly_x[1]], key=lambda w:w[0])
        values = [float(w[4].rstrip('%')) for w in row]
        assert len(values) == 13, (file,year,values)
        assert values == by_line[year], (file,year,values,by_line[year])
        returns = np.asarray(values[:12])/100
        published = values[12]/100
        low = float(np.prod(1+returns-.00005)-1-.00005)
        high = float(np.prod(1+returns+.00005)-1+.00005)
        assert low <= published <= high, (file,year,published,low,high)
        checks.append({'year':year,'published_annual_percent':values[12],
                       'compounded_rounded_monthly_percent':float((np.prod(1+returns)-1)*100),
                       'annual_within_rounding_bounds':True})
        selected.extend((f'{year}-{month:02d}',float(returns[month-1]))for month in range(1,13))
    assert len(selected) == 12*len(years) and len(dict(selected)) == 12*len(years)
    return selected,checks


def xlsx_reference(file):
    """Independent standard-library OOXML check of all 600 SDF values."""
    ns = {'m':'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}
    with zipfile.ZipFile(file) as archive:
        sheet = ET.fromstring(archive.read('xl/worksheets/sheet1.xml'))
        sdf = {}
        for cell in sheet.findall('m:sheetData/m:row/m:c',ns):
            if re.fullmatch(r'B\d+',cell.attrib['r']):
                value=cell.find('m:v',ns)
                if value is not None and cell.attrib.get('t') not in ('s','str','inlineStr'):
                    sdf[int(cell.attrib['r'][1:])]=float(value.text)
    return sdf


def support(values, cash=None):
    x=[float(v) for v in values]
    out={'months':len(x),'mean':mean(x),'sample_sd':stdev(x),'zero_h':mean(x)/stdev(x),
         'minimum_return':min(x),'maximum_return':max(x)}
    assert np.isclose(out['zero_h'],np.mean(x)/np.std(x,ddof=1),atol=1e-14)
    if cash is not None:
        excess=[a-float(b) for a,b in zip(x,cash)]
        out['monthly_excess_sharpe']=mean(excess)/stdev(excess)
        assert np.isclose(out['monthly_excess_sharpe'],np.mean(excess)/np.std(excess,ddof=1),atol=1e-14)
    else:
        out['monthly_excess_sharpe']=out['zero_h']
    return out


def main():
    cash,cash_source=monthly_french_cash()
    metadata={}
    all_rows=[]
    warmup_rows=[]
    warmup_checks={}
    specs={
        'BH_Macro_USD':('bhmacro_202601.pdf',4,(40,333,543,550),60,(65,540),(333,550)),
        'Winton_Alma_I1C_U':('winton_202609.pdf',2,(25,230,530,410),50,(60,530),(230,410)),
        'Parus_I_USD':('parus_202609.pdf',0,(28,447,447,615),50,(55,447),(447,615)),
    }
    for name,spec in specs.items():
        values,annual_checks=extract_pdf(spec)
        summary=support([x[1]for x in values],[cash[x[0]]for x in values])
        metadata[name]={'start':'2017-01','end':'2025-12',**summary,
                        'annual_reconciliations':annual_checks,
                        'two_independent_pdf_extractions_agree':True,
                        'source_file':f'data/external/{spec[0]}','source_page':spec[1]+1}
        all_rows.extend({'series':name,'month':m,'reported_total_return':r,
                         'usd_rf':cash[m],'excess_return':r-cash[m],
                         'currency':'USD','source_rounding_percent':.01}for m,r in values)
        warmup,checks2016=extract_pdf(spec,years=[2016])
        warmup=[(m,r)for m,r in warmup if '2016-07'<=m<='2016-12']
        assert len(warmup)==6
        warmup_rows.extend({'series':name,'month':m,'reported_total_return':r,
                            'usd_rf':cash[m],'excess_return':r-cash[m],
                            'currency':'USD','source_rounding_percent':.01}for m,r in warmup)
        warmup_checks[name]={'start':'2016-07','end':'2016-12','months':6,
                              'independent_pdf_extraction_match':True,
                              'annual_2016_reconciliation':checks2016[0]}
    frame=pd.DataFrame(all_rows)
    frame.to_csv(RAW/'public_nav_monthly_2017_2025.csv',index=False,float_format='%.17g')
    pd.DataFrame(warmup_rows).to_csv(RAW/'public_nav_warmup_2016.csv',index=False,float_format='%.17g')
    metadata['public_nav_warmup']={'file':'data/external/public_nav_warmup_2016.csv',
                                   'rows':18,'source_is_actual_2016_reported_returns':True,
                                   'no_imputation':True,'series':warmup_checks}
    # Keep the exact pre-existing cash vintage used in the main comparison.
    pd.DataFrame({'month':pd.period_range('2017-01','2025-12',freq='M').astype(str)}).assign(
        usd_rf=lambda d:d.month.map(cash)).to_csv(RAW/'usd_rf_2017_2025.csv',index=False,float_format='%.17g')
    xlsx=RAW/'cpz_sdf_timeseries.xlsx'
    source=pd.read_excel(xlsx,header=6)
    columns=['month','SDF']+[f'EW_beta_decile_{i:02d}'for i in range(1,11)]+[f'VW_beta_decile_{i:02d}'for i in range(1,11)]+[f'macro_{i}'for i in range(1,5)]
    source.columns=columns
    source=source.loc[source.SDF.notna()].copy()
    source['month']=pd.to_datetime(source.month).dt.to_period('M').astype(str)
    assert len(source)==600 and not source.month.duplicated().any()
    assert source.month.tolist()==pd.period_range('1967-01','2016-12',freq='M').astype(str).tolist()
    reference=xlsx_reference(xlsx)
    assert len(reference)==600
    assert all(float(v)==reference[int(i)+9] for i,v in enumerate(source.SDF))
    source.iloc[:,:22].to_csv(RAW/'cpz_published_monthly_1967_2016.csv',index=False,float_format='%.17g')
    cpz={}
    for label,start,end in [('paper_test','1992-01','2016-12'),('last_108','2008-01','2016-12'),('last_60','2012-01','2016-12')]:
        data=source.loc[source.month.between(start,end)]
        cpz[label]={'start':start,'end':end,'SDF':support(data.SDF),
                    'portfolio_count':21,'no_overlap_2017_2025':True}
    metadata['CPZ_GAN_SDF']=cpz
    metadata['CPZ_GAN_SDF']['independent_OOXML_SDF_values_exact_match']=600
    jkp_path=RAW/'jkp_world_all_factors_monthly_vwcap.csv'
    jkp=pd.read_csv(jkp_path,float_precision='round_trip')
    assert not jkp.duplicated(['name','date']).any()
    jkp['month']=pd.to_datetime(jkp.date).dt.to_period('M').astype(str)
    jkp=jkp.loc[jkp.month.between('2017-01','2025-12')].copy()
    assert jkp.name.nunique()==153 and len(jkp)==153*108 and jkp.ret.notna().all()
    assert jkp.groupby('name').size().eq(108).all()
    # Parse every included source value separately with the standard library.
    with jkp_path.open(encoding='utf-8',newline='')as handle:
        direct={(row['date'][:7],row['name']):float(row['ret'])for row in csv.DictReader(handle)
                if '2017-01'<=row['date'][:7]<='2025-12'}
    assert len(direct)==16524
    assert all(float(row.ret)==direct[(row.month,row['name'])]for _,row in jkp.iterrows())
    prepared=jkp.rename(columns={'name':'factor'})[['month','factor','ret']].sort_values(['month','factor'])
    prepared.to_csv(RAW/'jkp_world_monthly_2017_2025.csv',index=False,float_format='%.17g')
    metadata['JKP_world']={'months':108,'start':'2017-01','end':'2025-12','strategies':153,
                           'source_rows_checked_independently':16524,
                           'no_missing_returns':True,'no_duplicate_factor_months':True,
                           'no_sign_change_no_scaling_no_RF_subtraction':True,
                           'curated_file':'data/external/jkp_world_monthly_2017_2025.csv',
                           'raw_file':'data/external/jkp_world_all_factors_monthly_vwcap.csv'}
    metadata['cash_source']={'file':str(cash_source.relative_to(A9)),
                             'sha256':sha256(cash_source.read_bytes()).hexdigest(),
                             'percent_to_decimal':100,'same_vintage_as_assignment9':True}
    metadata['no_screen_scores_computed']=True
    (ROOT/'research/external_support_summary.json').write_text(json.dumps(metadata,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({k:{a:b for a,b in v.items()if a!='annual_reconciliations'}for k,v in metadata.items()if isinstance(v,dict)},indent=2))


if __name__=='__main__':
    main()
