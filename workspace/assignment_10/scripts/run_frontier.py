"""Chronological screening comparison; choices are made before evaluation outcomes."""
from math import comb
import argparse
import json
import time

import numpy as np
import pandas as pd

from frontier_engine import (ROOT,design,inputs,fit_reference,policy_training,observed_window,
    performance_groups,warning_statistics,apply_policy,calendar_indices,dependency_hashes)
from frontier_metrics import raw_scores,rank_scores,combine_scores,conservative_cutoffs


def periods():
    d=design()
    return {p:d[p] for p in ['development','calibration','evaluation']}


def configs(weighting):
    for length in design()['window_lengths']:
        for block in [12,6]:
            for representation in ['spread','funded']:
                yield length,block,representation,f'{weighting}_{representation}_{length}_b{block}'


def selected_weights(h,k):
    n=h.shape[-1]
    order=np.argsort(-h,axis=-1,kind='stable')
    inverse=np.empty_like(order)
    np.put_along_axis(inverse,order,np.broadcast_to(np.arange(n),order.shape),axis=-1)
    w=np.array([comb(n-j-1,k-1)/comb(n,k) if n-j>=k else 0 for j in range(n)])
    assert np.isclose(w.sum(),1)
    return w[inverse]


def selection_cutoffs(reference):
    d=design();specs=d['policies'];budgets=d['headline_budgets']
    values=combine_scores(reference['ranks'],specs,reference['pca'])
    n=values.shape[1];pools=sorted(set(min(n,k) for k in d['selection_sensitivity']['pool_sizes']))
    weights={k:selected_weights(reference['h'],k).ravel() for k in pools}
    rows=[];worst=np.full((len(specs),len(budgets)),-np.inf)
    for j,spec in enumerate(specs):
        flattened=values[...,j].ravel();order=np.argsort(flattened,kind='stable')
        ordered=flattened[order]
        for k in pools:
            cumulative=np.cumsum(weights[k][order]);cut=np.searchsorted(cumulative,(1-np.asarray(budgets))*cumulative[-1],side='left')
            cut=ordered[np.clip(cut,0,len(ordered)-1)]
            worst[j]=np.maximum(worst[j],cut)
            for b,c in zip(budgets,cut): rows.append(dict(policy=spec['id'],K=k,budget=b,cutoff=float(c)))
    return worst,rows


def core(weighting):
    started=time.monotonic();d=design();panel,cash=inputs(weighting,d['core_signals'])
    rate_rows=[];curve_rows=[];cutoff_rows=[];choice_rows=[];selection_rows=[];ledger=[];supports=[]
    policy_lookup={p['id']:p for p in d['reporting_policies']}
    for length,block,representation,namespace in configs(weighting):
        draws=d['bootstrap']['calibration_draws_primary' if block==12 else 'calibration_draws_secondary']
        reference=fit_reference(panel,cash,length,block,draws,representation,periods(),namespace)
        for j,spec in enumerate(d['policies']):
            for bi,budget in enumerate(d['budgets']):
                cutoff_rows.append(dict(weighting=weighting,representation=representation,months=length,block=block,
                    policy=spec['id'],families=spec['count'],primary=spec['primary'],budget=budget,
                    cutoff=float(reference['cutoffs'][j,bi]),calibration_rate=float(reference['calibration_rates'][j,bi])))
        print(json.dumps(dict(stage='reference_complete',configuration=namespace,seconds=time.monotonic()-started)),flush=True)
        if block!=12: continue
        _,choices=policy_training(panel,cash,reference,length,representation,d['calibration'],d['bootstrap']['policy_training_draws'])
        choice_rows.extend([dict(weighting=weighting,representation=representation,months=length,**row) for row in choices])
        worst,selection_reference=selection_cutoffs(reference)
        selection_rows.extend([dict(weighting=weighting,representation=representation,months=length,stage='cutoff',**row) for row in selection_reference])
        if length==108: ends=['2025-12']
        else: ends=[f'{year}-12' for year in range(2021,2026)]
        for end in ends:
            full,h=observed_window(panel,cash,end,length,representation)
            base=combine_scores(rank_scores(raw_scores(full[:,6:])[0],reference['maps']),d['policies'],reference['pca'])
            groups=performance_groups(h)
            rng=np.random.default_rng(np.random.SeedSequence([d['seed'],3,length,int(end[:4])]))
            picks=rng.random(full.shape)
            alterations={'unmodified':(full[:,6:],np.zeros(len(h),dtype=bool),dict(max_error=0,closing_gap=0))}
            for policy in d['reporting_policies']:
                alterations[policy['id']]=apply_policy(full,policy,length,picks=picks,funded=representation=='funded')
            supports.append(dict(weighting=weighting,representation=representation,months=length,end=end,n=len(h),
                max_excess_sharpe=float(h.max()),median_excess_sharpe=float(np.median(h)),top_quintile_cutoff=float(np.sort(h)[-int(np.ceil(len(h)/5))])))
            for mechanism,(altered,changed,audit) in alterations.items():
                scores=base if mechanism=='unmodified' else combine_scores(rank_scores(raw_scores(altered)[0],reference['maps']),d['policies'],reference['pca'])
                rows=warning_statistics(base,scores,changed,reference['cutoffs'],[1,5,10],groups)
                extra=dict(weighting=weighting,representation=representation,months=length,end=end,mechanism=mechanism)
                rate_rows.extend([dict(**extra,**row) for row in rows])
                ledger.append(dict(**extra,**audit,changed=int(changed.sum())))
                if weighting=='original' and representation=='spread' and length==108 and mechanism in ['unmodified','relative_permanent','relative_delay3','smooth50','fixed_delay3']:
                    rows=warning_statistics(base,scores,changed,reference['cutoffs'],range(101),{k:v for k,v in groups.items() if k!='remaining'})
                    curve_rows.extend([dict(**extra,**row) for row in rows])
                if end=='2025-12' and mechanism in ['unmodified','relative_delay3','smooth50']:
                    for k in [1,20,len(h)]:
                        w=selected_weights(h[None,:],k)[0]
                        for j,spec in enumerate(d['policies']):
                            for bi,budget in enumerate(d['headline_budgets']):
                                cut=worst[j,bi]
                                selection_rows.append(dict(weighting=weighting,representation=representation,months=length,stage='evaluation',
                                    mechanism=mechanism,policy=spec['id'],K=k,budget=budget,cutoff=float(cut),
                                    baseline_rate=float(w@(base[:,j]>cut)),altered_rate=float(w@(scores[:,j]>cut))))
    for name,rows in [('point_rates',rate_rows),('frontier_curves',curve_rows),('cutoffs',cutoff_rows),
                      ('policy_choices',choice_rows),('selection_sensitivity',selection_rows),('reporting_ledger',ledger),('performance_support',supports)]:
        if rows: pd.DataFrame(rows).to_csv(ROOT/f'tables/{name}_{weighting}.csv',index=False)
    result=dict(status='complete',weighting=weighting,seconds=time.monotonic()-started,
                rate_rows=len(rate_rows),curve_rows=len(curve_rows),dependencies=dependency_hashes())
    (ROOT/f'data/execution_{weighting}.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result),flush=True)


def cross_folds():
    started=time.monotonic();d=design();panel,cash=inputs('original',d['core_signals'])
    rows=[];choice_rows=[];ledger=[]
    for fold in range(5):
        train=[n for n in d['core_signals'] if d['strategy_folds'][n]!=fold]
        test=[n for n in d['core_signals'] if d['strategy_folds'][n]==fold]
        reference=fit_reference(panel[train],cash,108,12,d['bootstrap']['fold_calibration_draws'],'spread',periods(),f'fold{fold}')
        _,choices=policy_training(panel[train],cash,reference,108,'spread',d['calibration'],d['bootstrap']['fold_policy_training_draws'])
        choice_rows.extend([dict(fold=fold,training_strategies=len(train),test_strategies=len(test),**row) for row in choices])
        full,h=observed_window(panel[test],cash,'2025-12',108,'spread')
        base=combine_scores(rank_scores(raw_scores(full[:,6:])[0],reference['maps']),d['policies'],reference['pca'])
        picks=np.random.default_rng(d['seed']+fold+500).random(full.shape)
        for policy in [None]+d['reporting_policies']:
            mechanism='unmodified' if policy is None else policy['id']
            altered,changed,audit=(full[:,6:],np.zeros(len(test),bool),dict(max_error=0,closing_gap=0)) if policy is None else apply_policy(full,policy,108,picks=picks)
            scores=base if policy is None else combine_scores(rank_scores(raw_scores(altered)[0],reference['maps']),d['policies'],reference['pca'])
            for choice in choices:
                if choice['left_out']!='none': continue
                j=choice['policy_index'];bi=int(round(100*choice['budget']));cut=reference['cutoffs'][j,bi]
                before=base[:,j]>cut;after=scores[:,j]>cut
                rows.append(dict(fold=fold,mechanism=mechanism,scope=choice['scope'],budget=choice['budget'],policy=choice['policy'],
                    families=choice['families'],n=len(test),baseline=int(before.sum()),altered=int(after.sum()),new=int((after&~before).sum()),
                    cleared=int((before&~after).sum()),changed=int(changed.sum()),cutoff=float(cut)))
            ledger.append(dict(fold=fold,mechanism=mechanism,**audit))
        print(json.dumps(dict(stage='strategy_fold_complete',fold=fold,seconds=time.monotonic()-started)),flush=True)
    for name,data in [('strategy_fold_rates',rows),('strategy_fold_choices',choice_rows),('strategy_fold_ledger',ledger)]:
        pd.DataFrame(data).to_csv(ROOT/f'tables/{name}.csv',index=False)
    (ROOT/'data/execution_folds.json').write_text(json.dumps(dict(status='complete',seconds=time.monotonic()-started,dependencies=dependency_hashes()),indent=2)+'\n')


def uncertainty():
    started=time.monotonic();d=design();panel,cash=inputs('original',d['core_signals'])
    reference=fit_reference(panel,cash,108,12,d['bootstrap']['calibration_draws_primary'],'spread',periods(),'original_spread_108_b12')
    choice=pd.read_csv(ROOT/'tables/policy_choices_original.csv')
    choice=choice[(choice.months==108)&(choice.representation=='spread')&(choice.left_out=='none')]
    singles={float(row.budget):int(row.policy_index) for row in choice[choice.scope.astype(str)=='1'].itertuples()}
    source=panel.loc['2017-01':'2025-12'].to_numpy();warm=panel.loc['2016-07':'2025-12'].to_numpy()
    policies=[p for p in d['reporting_policies'] if p['id'] in ['relative_permanent','relative_delay3','smooth50','fixed_delay3']]
    draws=d['bootstrap']['evaluation_draws'];cut=reference['cutoffs'][:,[1,5,10]]
    records={};rng=np.random.default_rng(np.random.SeedSequence([d['seed'],4]))
    for start in range(0,draws,25):
        n=min(25,draws-start);ix=calendar_indices(rng,n,108,108,12)
        previous=(ix[:,:1]+np.arange(0,6)[None,:])
        full=np.concatenate([warm[previous].transpose(0,2,1),source[ix].transpose(0,2,1)],axis=-1)
        base_raw,details=raw_scores(full[...,6:]);base=combine_scores(rank_scores(base_raw,reference['maps']),d['policies'],reference['pca'])
        before=base[...,None]>cut[None,None,:,:]
        high=np.zeros((n,194),bool);order=np.argsort(-details['h'],axis=1,kind='stable');np.put_along_axis(high,order[:,:39],True,axis=1)
        group_masks=dict(all=np.ones_like(high),top_quintile=high)
        for policy in policies:
            altered,changed,_=apply_policy(full,policy,108)
            scores=combine_scores(rank_scores(raw_scores(altered)[0],reference['maps']),d['policies'],reference['pca'])
            after=scores[...,None]>cut[None,None,:,:];new=after&~before
            for group,mask in group_masks.items():
                denom=mask.sum(axis=1)[:,None,None]
                for name,array in [('baseline',before),('altered',after),('new',new)]:
                    values=(array*mask[...,None,None]).sum(axis=1)/denom
                    records.setdefault((policy['id'],group,name),[]).append(values)
        print(json.dumps(dict(stage='paired_bootstrap',draws=start+n,seconds=time.monotonic()-started)),flush=True)
    rows=[]
    for mechanism in [p['id'] for p in policies]:
        for group in ['all','top_quintile']:
            arrays={name:np.concatenate(records[(mechanism,group,name)]) for name in ['baseline','altered','new']}
            for bi,budget in enumerate(d['headline_budgets']):
                benchmark=singles[budget]
                differences=arrays['new'][:,:,bi]-arrays['new'][:,benchmark,bi,None]
                center=differences.mean(axis=0)
                width=float(np.quantile(np.max(np.abs(differences-center),axis=1),.95))
                for j,spec in enumerate(d['policies']):
                    row=dict(mechanism=mechanism,group=group,policy=spec['id'],budget=budget,draws=draws,
                        benchmark_single=d['policies'][benchmark]['id'],mean_paired_new_gain=float(center[j]),
                        paired_gain_lo=float(np.quantile(differences[:,j],.025)),paired_gain_hi=float(np.quantile(differences[:,j],.975)),
                        simultaneous_halfwidth=width,simultaneous_gain_lo=float(center[j]-width),simultaneous_gain_hi=float(center[j]+width))
                    for name,values in arrays.items():
                        row.update({name+'_mean':float(values[:,j,bi].mean()),name+'_lo':float(np.quantile(values[:,j,bi],.025)),name+'_hi':float(np.quantile(values[:,j,bi],.975))})
                    rows.append(row)
    pd.DataFrame(rows).to_csv(ROOT/'tables/paired_bootstrap.csv',index=False)
    (ROOT/'data/execution_uncertainty.json').write_text(json.dumps(dict(status='complete',seconds=time.monotonic()-started,dependencies=dependency_hashes()),indent=2)+'\n')


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--stage',choices=['core','folds','uncertainty'],required=True)
    parser.add_argument('--weighting',choices=['original','value_weighted'],default='original')
    args=parser.parse_args()
    if args.stage=='core': core(args.weighting)
    elif args.stage=='folds': cross_folds()
    else: uncertainty()


if __name__=='__main__': main()
