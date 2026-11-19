"""Preserve the frontier design before inspecting its screening outcomes."""
from datetime import datetime,timezone
from hashlib import sha256
from pathlib import Path
import json
import shutil

import numpy as np
import pandas as pd
from frontier_metrics import policy_specs

ROOT=Path(__file__).resolve().parents[1]
OLD=ROOT.parent/'assignment_9'


def main():
    target=ROOT/'data/frozen_design.json'
    if target.exists():
        raise RuntimeError('Frozen design already exists')
    for folder in ['data/raw','data/cache','tables','figures','research','scripts']:
        (ROOT/folder).mkdir(parents=True,exist_ok=True)
    names=json.loads((OLD/'data/frozen_design.json').read_text())['core_signals']
    documents=pd.read_csv(OLD/'data/raw/SignalDoc.csv').set_index('Acronym').loc[names]
    category=documents['Cat.Economic'].fillna('other')
    sizes=category.value_counts()
    assignment={};loads=[0]*5
    for group,n in sorted(sizes.items(),key=lambda item:(-item[1],item[0])):
        fold=min(range(5),key=lambda k:(loads[k],k))
        assignment[group]=fold;loads[fold]+=int(n)
    folds={name:assignment[category.loc[name]] for name in names}
    sources=[]
    for name in ['PredictorLSretWide.parquet','PredictorVWforce.parquet','SignalDoc.csv',
                 'F-F_Research_Data_Factors.csv','F-F_Research_Data_Factors_CSV.zip',
                 'fund_x_2017_01_to_2026_09.csv']:
        source=OLD/'data/raw'/name;destination=ROOT/'data/raw'/name
        shutil.copy2(source,destination)
        sources.append(dict(file=destination.relative_to(ROOT).as_posix(),
                            bytes=destination.stat().st_size,sha256=sha256(destination.read_bytes()).hexdigest()))
    oldmeta=json.loads((OLD/'data/source_provenance.json').read_text())
    (ROOT/'data/source_provenance.json').write_text(json.dumps(dict(source_assignment=9,
        dataset_commit=oldmeta['dataset_commit'],source_metadata=oldmeta,sources=sources),indent=2)+'\n')
    policies=policy_specs()
    design=dict(assignment=10,frozen_utc=datetime.now(timezone.utc).isoformat(),
        status='frozen before any new frontier screening outcomes inspected; timing pilot discarded scores',
        seed=20261119,core_signals=names,strategy_category=category.to_dict(),strategy_folds=folds,fold_sizes=loads,
        data_release='2026.10',development=['1980-01','2004-12'],calibration=['2005-01','2016-12'],evaluation=['2017-01','2025-12'],
        window_lengths=[108,60],primary_months=108,
        representations=['spread','funded'],weightings=['original','value_weighted'],
        funding='RF+LS per equity1, long1 short1; source gross of trading/borrowing/management costs; no second RF subtraction',
        primitive_scores=dict(B='count[0,SD]/(1+count[-SD,0))',
            D='T*normalCDF(-mean/SD)-negative_count; paper Gaussian adaptation, not original Bollen-Pool',
            A='positive first-order demeaned sample autocorrelation; no causal smoothing interpretation',
            Z='[3(G1-L1)-(G2-L2)]/sqrt[9(G1+L1)+(G2+L2)]; b=.25SD, adjacent bins [-2b,-b),[-b,0),(0,b],(b,2b]; exact zeros separately; empirical score only'),
        local_bandwidth=.25,bandwidth_sensitivity=.5,
        maps='fixed right-inclusive empirical CDF per primitive, count<=score/(Ndevelopment+1), all complete December-ending windows',
        policies=policies,primary_policy_count=sum(x['primary'] for x in policies),total_policy_count=len(policies),
        secondary_comparators='equal mean ranks for11nonsingleton subsets; train-only standardized first principal component all4, sign sum(loadings)>=0; not an exact prior-paper replication',
        budgets=np.linspace(0,1,101).tolist(),headline_budgets=[.01,.05,.10],strict_exceedance=True,
        boundary='investigate-none at0% via+inf; investigate-all at100% via-inf; ties never split; report achieved rates',
        bootstrap=dict(calibration_draws_primary=5000,calibration_draws_secondary=3000,
            primary_block=12,secondary_block=6,evaluation_draws=500,policy_training_draws=400,fold_calibration_draws=1000,fold_policy_training_draws=200),
        selection_sensitivity=dict(pool_sizes=[1,5,20,50,100,194],budgets=[.01,.05,.10],
            reference='maximum separate weighted cutoff across declared K; winner highest original underlying excess Sharpe; no independence across strategies'),
        primary_reporting='risk-relative losses[-.25*baselineSD,0) replaced with+.0125*baselineSD, return full hidden amount after statedlag; underlying path fixed',
        reporting_policies=[
            dict(id='relative_permanent',kind='loss',scale='sd',bound=.25,gain=.0125,lag='permanent',p=1),
            dict(id='relative_delay1',kind='loss',scale='sd',bound=.25,gain=.0125,lag=1,p=1),
            dict(id='relative_delay3',kind='loss',scale='sd',bound=.25,gain=.0125,lag=3,p=1),
            dict(id='relative_delay6',kind='loss',scale='sd',bound=.25,gain=.0125,lag=6,p=1),
            dict(id='relative_half_delay3',kind='loss',scale='sd',bound=.25,gain=.0125,lag=3,p=.5),
            dict(id='fixed_permanent',kind='loss',scale='fixed',bound=.01,gain=.0005,lag='permanent',p=1),
            dict(id='fixed_delay3',kind='loss',scale='fixed',bound=.01,gain=.0005,lag=3,p=1),
            dict(id='smooth25',kind='smoothing',weight=.25),
            dict(id='smooth50',kind='smoothing',weight=.5),
            dict(id='smooth75',kind='smoothing',weight=.75)],
        training_mechanisms=['relative_permanent','relative_delay3','smooth50'],
        policy_selection='calibration only; maximize mean NEW-warning rate across training mechanisms at each budget; tie fewer families then alphabeticalID; also best fixedquantity andleave-one-mechanism-out',
        strategy_validation='5folds holding whole Cat.Economic families together, greedily balanced by count; fit maps, cutoffs and policy choice on remaining families only; evaluate their heldout2017-2025returns',
        performance_groups='all; strongest original-underlying-Sharpe quintile per review window; remaining80%; labels retained after reporting alteration; not a genuine FundX-level-fund label',
        evaluation_visibility='A9has already inspected2017-2025 descriptive andtwo-rule results; this is a new frozen comparison, not a virgin sample',
        uncertainty='paired joint calendar12month bootstrap; fixed old maps/cutoffs/policy choices; changed-only andall-path counts separately; strategy rows are not independent',
        frontiers='fixed old-cutoff out-of-time operating curves; descriptive test envelope is not a deployable selectedpolicy; compare achieved baseline warning andaltered warning jointly',
        external_validation=dict(status='separatelylabelled source-transfer evidence, source acceptance before screenoutcomes',
            live_navs='public USDnet NAVs2017-2025 apply frozen global choices; no retuning',
            cpz='authornormalizedSDFexcesspayoff gross stocknotional1, notnetNAV; development1926-1979/calibration1980-1991 from completeCZreference; evaluatepublishedtest1992-2016, nonoverlap108blocksfromstart plusfinal108sensitivity; full300separatelength reference; performance outcomes allowed for source-support search, screens notinspected',
            cpz_lengths=[108,300],cpz_development=['1926-01','1979-12'],cpz_calibration=['1980-01','1991-12']),
        novelty_target='robust new empirical operating dominance/quantity saturation/mechanism-transfer failure or performance-dependent degradation; not frontier method or score aggregation',
        economic_scope='benchmark investigation burden, not observedfraudprevalence or optimum real-world operational checks',
        runtime='timingpilot projected7.35min local; CPU26if actual remainingwork projected>10min; no remote credentials in results')
    assert design['primary_policy_count']==26 and design['total_policy_count']==38
    target.write_text(json.dumps(design,indent=2)+'\n')
    print(json.dumps(dict(status='frozen',primary_policies=26,total_policies=38,fold_sizes=loads,
                         sha256=sha256(target.read_bytes()).hexdigest()),indent=2))


if __name__=='__main__':
    main()
