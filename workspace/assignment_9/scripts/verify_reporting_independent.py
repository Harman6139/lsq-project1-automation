"""Reconstruct reporting counts directly, without using the reporting engine."""
from math import comb
from pathlib import Path
import json

import numpy as np
import pandas as pd
from scipy.stats import binom, norm

from a9_data import ROOT, load_panel, read_design, read_french


def flags_from_values(values, maps, cutoffs):
    n = values.shape[1]
    mean = np.mean(values, axis=1)
    sd = np.std(values, axis=1, ddof=1)
    lower = np.sum((values >= -sd[:,None]) & (values < 0), axis=1)
    upper = np.sum((values >= 0) & (values <= sd[:,None]), axis=1)
    B = upper/(lower+1)
    losses = np.sum(values < 0, axis=1)
    D = n*norm.cdf(-mean/sd)-losses
    P = binom.cdf(losses,n,norm.cdf(-mean/sd))
    rank_B = np.searchsorted(maps[0],B,side='right')/(len(maps[0])+1)
    rank_D = np.searchsorted(maps[1],D,side='right')/(len(maps[1])+1)
    C = np.maximum(rank_B,rank_D)
    return {'conventional_bias':B>2, 'conventional_normal':P<.05,
            'conventional_any':(B>2)|(P<.05), 'ordinary_calibrated':C>cutoffs['ordinary'],
            'selection_calibrated':C>cutoffs['selection']}


def main():
    design=read_design()
    locks=json.loads((ROOT/'data/locked_cutoffs.json').read_text())['rules']
    point=pd.read_csv(ROOT/'tables/reporting_point.csv',float_precision='round_trip')
    selected=pd.read_csv(ROOT/'tables/reporting_selection.csv',float_precision='round_trip')
    french=read_french()
    names=list(load_panel('original').columns)
    picks=np.random.default_rng(np.random.SeedSequence([design['seed'],9,1])).random((len(names),114))
    checked=0
    selected_checked=0
    max_accounting_error=0.0
    for weighting in ['original','value_weighted']:
        frame=load_panel(weighting).loc['2016-07':'2025-12']
        cash=french.reindex(frame.index)['RF'].to_numpy()
        for months in [108,60]:
            raw=frame.to_numpy().T[:,-(months+6):]
            rf=cash[-(months+6):]
            common=picks[:,-(months+6):]
            for kind in ['spread','funded']:
                values=raw if kind=='spread' else raw+rf[None,:]
                coordinate=values if kind=='spread' else np.log1p(values)
                target=.0005 if kind=='spread' else np.log1p(.0005)
                with np.load(ROOT/f'data/maps/{weighting}_{kind}_{months}.npz') as data:
                    maps=(data['B'],data['D'])
                cutoff=locks[f'{weighting}:{kind}:{months}:b12']
                before=flags_from_values(values[:,6:],maps,cutoff)
                for probability in [1.,.5]:
                    for delta in [.005,.01,.02]:
                        hidden=(values>=-delta)&(values<0)&(common<probability)
                        q=np.where(hidden,target-coordinate,0.)
                        for lag in ['permanent','1','3','6']:
                            release=np.zeros_like(q)
                            if lag!='permanent':
                                L=int(lag)
                                release[:,L:]=q[:,:-L]
                                opening=q[:,max(0,6-L):6].sum(axis=1)
                                closing=q[:,-L:].sum(axis=1)
                            else:
                                opening=q[:,:6].sum(axis=1)
                                closing=q.sum(axis=1)
                            reported_coordinate=coordinate+q-release
                            reported=reported_coordinate if kind=='spread' else np.expm1(reported_coordinate)
                            observed=reported[:,6:]
                            difference=(reported_coordinate[:,6:]-coordinate[:,6:]).sum(axis=1)
                            max_accounting_error=max(max_accounting_error,float(np.max(np.abs(difference-closing+opening))))
                            changed=np.any(np.abs(observed-values[:,6:])>1e-14,axis=1)
                            after=flags_from_values(observed,maps,cutoff)
                            rows=point.loc[(point.weighting==weighting)&(point.representation==kind)
                                           &(point.months==months)&(point.probability==probability)
                                           &(point.delta==delta)&(point.lag==lag)]
                            assert len(rows)==5
                            for row in rows.itertuples():
                                b,a=before[row.method],after[row.method]
                                assert row.n_strategies==len(a)
                                assert row.baseline_alerts==int(b.sum())
                                assert row.altered_alerts==int(a.sum())
                                assert row.new_alerts==int((~b&a).sum())
                                assert row.cleared_alerts==int((b&~a).sum())
                                assert row.changed_paths==int(changed.sum())
                                checked+=1
                            if months!=108 or probability!=1 or delta!=.01:
                                continue
                            base_h=raw[:,6:].mean(axis=1)/raw[:,6:].std(axis=1,ddof=1)
                            excess=observed if kind=='spread' else observed-rf[None,6:]
                            altered_h=excess.mean(axis=1)/excess.std(axis=1,ddof=1)
                            altered_h[~changed]=base_h[~changed]
                            for K in [20,100,len(base_h)]:
                                probs=[]
                                for i,h in enumerate(altered_h):
                                    lower=sum(j!=i and (base_h[j]<h or (base_h[j]==h and j>i)) for j in range(len(base_h)))
                                    probs.append(comb(lower,K-1)/comb(len(base_h)-1,K-1) if lower>=K-1 else 0.)
                                probs=np.array(probs)
                                group=selected.loc[(selected.weighting==weighting)&(selected.representation==kind)
                                                   &(selected.lag==lag)&(selected.K==K)]
                                assert len(group)==5
                                for row in group.itertuples():
                                    joint=float(np.mean(probs*after[row.method]))
                                    np.testing.assert_allclose(row.designated_candidate_selection_probability,probs.mean(),rtol=0,atol=1e-15)
                                    np.testing.assert_allclose(row.joint_selected_alert_probability,joint,rtol=0,atol=1e-15)
                                    if probs.mean()>0:
                                        np.testing.assert_allclose(row.conditional_alert_given_selected,joint/probs.mean(),rtol=0,atol=2e-14)
                                    selected_checked+=1
    result=dict(point_rows_recomputed=checked,selected_policy_rows_recomputed=selected_checked,
                maximum_direct_ledger_error=max_accounting_error,
                independent_of_reporting_module=True,actual_point_denominator=len(names))
    assert checked==960 and selected_checked==240
    assert max_accounting_error<1e-12
    output=ROOT/'data/independent_verification.json'
    evidence=json.loads(output.read_text())
    evidence['independent_reporting']=result
    output.write_text(json.dumps(evidence,indent=2)+'\n')
    print(json.dumps(result,indent=2))


if __name__=='__main__':
    main()
