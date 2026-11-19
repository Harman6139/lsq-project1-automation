"""Source-transfer checks: published GAN factor, world factors, net NAVs and Fund X."""
from hashlib import sha256
import json
import time

import numpy as np
import pandas as pd

from frontier_engine import (ROOT,design,inputs,fit_reference,policy_training,observed_window,
    performance_groups,warning_statistics,apply_policy,dependency_hashes)
from frontier_metrics import raw_scores,rank_scores,combine_scores


def freeze_external_inputs():
    paths=['data/external/cpz_published_monthly_1967_2016.csv',
           'data/external/jkp_world_all_factors_monthly_vwcap.csv',
           'data/external/public_nav_monthly_2017_2025.csv',
           'data/external/public_nav_warmup_2016.csv']
    record=dict(status='accepted before new screening outcomes inspected',
                support_search='Sharpe ratios inspected to establish coverage, not to select screen outcomes',
                files=[dict(file=p,sha256=sha256((ROOT/p).read_bytes()).hexdigest()) for p in paths])
    target=ROOT/'data/external_validation_inputs.json'
    if target.exists():
        if json.loads(target.read_text())!=record: raise RuntimeError('External inputs changed')
    else: target.write_text(json.dumps(record,indent=2)+'\n')


def main():
    freeze_external_inputs();started=time.monotonic();d=design()
    panel,cash=inputs('original',d['core_signals'])
    primary_periods={p:d[p] for p in ['development','calibration','evaluation']}
    references={kind:fit_reference(panel,cash,108,12,d['bootstrap']['calibration_draws_primary'],kind,
                    primary_periods,f'original_{kind}_108_b12') for kind in ['spread','funded']}
    accepted=[p for p in d['reporting_policies'] if p['id'] in ['relative_permanent','relative_delay3','relative_half_delay3','smooth50']]
    rows=[];support=[];old_choices=[];ledgers=[];primitive=[]

    def evaluate(source,label,full,underlying_h,reference,representation,groups,start,end,external_class,warmup=6):
        length=full.shape[-1]-warmup
        raw,details=raw_scores(full[:,warmup:])
        base=combine_scores(rank_scores(raw,reference['maps']),d['policies'],reference['pca'])
        ranks=rank_scores(raw,reference['maps'])
        names=list(underlying_h.index)
        for i,name in enumerate(names):
            support.append(dict(source=source,sample=label,series=name,months=length,start=start,end=end,
                mean=float(details['mean'][i]),sd=float(details['sd'][i]),zero_h=float(details['h'][i]),
                excess_sharpe=float(underlying_h.iloc[i]),data_class=external_class,representation=representation))
            primitive.append(dict(source=source,sample=label,series=name,months=length,
                **{field:float(raw[i,j]) for j,field in enumerate(['B','D','A','Z'])},
                **{field+'_rank':float(ranks[i,j]) for j,field in enumerate(['B','D','A','Z'])},
                negative=int(details['negative'][i]),exact_zeros=int(details['exact_zeros'][i])))
        rng=np.random.default_rng(np.random.SeedSequence([d['seed'],8,length,int(end[:4])]))
        picks=rng.random(full.shape)
        cases=[('unmodified',full[:,warmup:],np.zeros(len(full),bool),dict(max_error=0,closing_gap=0))]
        if source!='Fund_X':
            for policy in accepted:
                altered,changed,audit=apply_policy(full,policy,length,picks=picks,funded=representation=='funded')
                cases.append((policy['id'],altered,changed,audit))
        for mechanism,altered,changed,audit in cases:
            scores=base if mechanism=='unmodified' else combine_scores(rank_scores(raw_scores(altered)[0],reference['maps']),d['policies'],reference['pca'])
            extra=dict(source=source,sample=label,months=length,start=start,end=end,mechanism=mechanism,data_class=external_class,representation=representation)
            rows.extend([dict(**extra,**row) for row in warning_statistics(base,scores,changed,reference['cutoffs'],[1,5,10],groups)])
            ledgers.append(dict(**extra,**audit,changed=int(changed.sum())))

    # Independent global stock universe; the CZ rule and cutoff are untouched.
    jkp=pd.read_csv(ROOT/'data/external/jkp_world_all_factors_monthly_vwcap.csv',float_precision='round_trip')
    jkp.index=pd.to_datetime(jkp.date).dt.to_period('M')
    jkp['month']=jkp.index.astype(str)
    world=jkp.pivot(index='month',columns='name',values='ret')
    world.index=pd.PeriodIndex(world.index,freq='M');world=world.sort_index()
    good=world.loc['2016-07':'2025-12'].notna().all()
    world=world.loc[:,good]
    assert world.loc['2017-01':'2025-12'].shape==(108,153)
    full=world.loc['2016-07':'2025-12'].to_numpy().T
    h=pd.Series(full[:,6:].mean(axis=1)/full[:,6:].std(axis=1,ddof=1),index=world.columns)
    evaluate('JKP_world','2017_2025',full,h,references['spread'],'spread',performance_groups(h.to_numpy()),'2017-01','2025-12','published_global_stock_backtests_gross')

    # Independently published net USD NAV records; use the funded-return reference.
    nav=pd.concat([pd.read_csv(ROOT/'data/external/public_nav_warmup_2016.csv',float_precision='round_trip'),
                   pd.read_csv(ROOT/'data/external/public_nav_monthly_2017_2025.csv',float_precision='round_trip')])
    nav.index=pd.PeriodIndex(nav.month,freq='M')
    total=nav.pivot(index='month',columns='series',values='reported_total_return');total.index=pd.PeriodIndex(total.index,freq='M');total=total.sort_index()
    excess=nav.pivot(index='month',columns='series',values='excess_return');excess.index=pd.PeriodIndex(excess.index,freq='M');excess=excess.sort_index()
    full=total.loc['2016-07':'2025-12'].to_numpy().T
    assert full.shape==(3,114) and np.isfinite(full).all()
    h=excess.loc['2017-01':'2025-12'].mean()/excess.loc['2017-01':'2025-12'].std(ddof=1)
    groups={'all':np.ones(3,bool)}
    groups.update({name:np.arange(3)==i for i,name in enumerate(total.columns)})
    evaluate('public_NAV','2017_2025',full,h,references['funded'],'funded',groups,'2017-01','2025-12','published_net_USD_NAV')

    # Fund X is a case application only, not a known unaltered record.
    fund=pd.read_csv(ROOT/'data/raw/fund_x_2017_01_to_2026_09.csv',float_precision='round_trip')
    fund.index=pd.PeriodIndex(fund.date,freq='M');r=fund.lsq_return.loc['2017-01':'2025-12']
    # No pre-2017 Fund X months are supplied; only its actual baseline is evaluated.
    full=r.to_numpy()[None,:]
    excess=r-cash.reindex(r.index)
    evaluate('Fund_X','common108',full,pd.Series({'Fund X':excess.mean()/excess.std(ddof=1)}),references['funded'],
             'funded',{'case_only':np.ones(1,bool)},'2017-01','2025-12','reported_fund_returns_authenticity_unknown',warmup=0)

    # Old reference data precede the ENTIRE author-designated 1992-2016 test period.
    historical,cash=inputs('original')
    old_names=historical.loc['1980-01':'1991-12'].notna().all()
    historical=historical.loc[:,old_names]
    cpz=pd.read_csv(ROOT/'data/external/cpz_published_monthly_1967_2016.csv',float_precision='round_trip')
    cpz.index=pd.PeriodIndex(cpz.pop('month'),freq='M')
    old_periods=dict(development=['1926-01','1979-12'],calibration=['1980-01','1991-12'],evaluation=['1992-01','2016-12'])
    external_ref_metadata=[]
    for length in [108,300]:
        reference=fit_reference(historical,cash,length,12,d['bootstrap']['calibration_draws_primary'],'spread',old_periods,f'external_old_spread_{length}')
        _,choices=policy_training(historical,cash,reference,length,'spread',old_periods['calibration'],d['bootstrap']['policy_training_draws'])
        old_choices.extend([dict(months=length,**choice) for choice in choices])
        external_ref_metadata.append(dict(months=length,strategies=len(historical.columns),periods=old_periods,development=reference['map_metadata'],
                                         caveat='300-month reference draws resample144 historical calibration months; historical conditional extrapolation, not300new observed months'))
        samples=[('first108','1992-01','2000-12'),('second108','2001-01','2009-12'),('final108_overlap','2008-01','2016-12')] if length==108 else [('published_test300','1992-01','2016-12')]
        for label,start,end in samples:
            start_period=pd.Period(start,freq='M');end_period=pd.Period(end,freq='M')
            source=cpz.loc[start_period-6:end_period]
            full=source.to_numpy().T
            assert full.shape==(21,length+6) and np.isfinite(full).all()
            h=pd.Series(full[:,6:].mean(axis=1)/full[:,6:].std(axis=1,ddof=1),index=cpz.columns)
            group=dict(all21=np.ones(21,bool),SDF=np.arange(21)==0,beta_deciles=np.arange(21)!=0)
            evaluate('CPZ_author',label,full,h,reference,'spread',group,start,end,'normalized_gross_excess_payoff_historical_model_test')
            # Same-date unchanged CZ records show how far the old reference drifts.
            backdrop=historical.loc[start_period-6:end_period]
            good=backdrop.notna().all();backdrop=backdrop.loc[:,good]
            values=backdrop.to_numpy().T
            h=pd.Series(values[:,6:].mean(axis=1)/values[:,6:].std(axis=1,ddof=1),index=backdrop.columns)
            evaluate('historical_CZ',label,values,h,reference,'spread',performance_groups(h.to_numpy()),start,end,'historical_reference_stock_backtests')
        print(json.dumps(dict(stage='external_historical_complete',months=length,seconds=time.monotonic()-started)),flush=True)
    for name,data in [('external_rates',rows),('external_support',support),('external_primitive_scores',primitive),
                      ('external_policy_choices',old_choices),('external_reporting_ledger',ledgers)]:
        pd.DataFrame(data).to_csv(ROOT/f'tables/{name}.csv',index=False)
    (ROOT/'data/external_reference_metadata.json').write_text(json.dumps(external_ref_metadata,indent=2)+'\n')
    (ROOT/'data/execution_external.json').write_text(json.dumps(dict(status='complete',seconds=time.monotonic()-started,
        dependencies=dependency_hashes(),inputs=json.loads((ROOT/'data/external_validation_inputs.json').read_text())),indent=2)+'\n')
    print(json.dumps(dict(status='external_complete',seconds=time.monotonic()-started,rows=len(rows))),flush=True)


if __name__=='__main__': main()
