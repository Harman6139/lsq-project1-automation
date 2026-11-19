"""Frozen block/bandwidth checks without changing the candidate families or choices."""
import json
import time
import numpy as np
import pandas as pd
from frontier_engine import ROOT,design,inputs,fit_reference,observed_window,performance_groups,apply_policy,warning_statistics,dependency_hashes
from frontier_metrics import raw_scores,rank_scores,combine_scores


def main():
    started=time.monotonic();d=design();panel,cash=inputs('original',d['core_signals'])
    periods={p:d[p] for p in ['development','calibration','evaluation']}
    full,h=observed_window(panel,cash,'2025-12',108,'spread')
    picks=np.random.default_rng(d['seed']+900).random(full.shape)
    rows=[]
    for label,block,bandwidth,draws,namespace in [
            ('blocks6',6,.25,d['bootstrap']['calibration_draws_secondary'],'original_spread_108_b6'),
            ('bandwidth50',12,.5,d['bootstrap']['calibration_draws_primary'],'original_spread_108_b12_bw50')]:
        ref=fit_reference(panel,cash,108,block,draws,'spread',periods,namespace,bandwidth)
        base=combine_scores(rank_scores(raw_scores(full[:,6:],bandwidth)[0],ref['maps']),d['policies'],ref['pca'])
        for p in [None]+[p for p in d['reporting_policies'] if p['id'] in ['relative_permanent','relative_delay3','relative_half_delay3','smooth50','fixed_delay3']]:
            if p is None:
                altered=full[:,6:];changed=np.zeros(194,bool);mechanism='unmodified'
            else:
                altered,changed,_=apply_policy(full,p,108,picks=picks);mechanism=p['id']
            scores=base if p is None else combine_scores(rank_scores(raw_scores(altered,bandwidth)[0],ref['maps']),d['policies'],ref['pca'])
            rows.extend([dict(sensitivity=label,mechanism=mechanism,**r) for r in warning_statistics(base,scores,changed,ref['cutoffs'],[1,5,10],performance_groups(h))])
    pd.DataFrame(rows).to_csv(ROOT/'tables/block_bandwidth_sensitivity.csv',index=False)
    (ROOT/'data/execution_sensitivity.json').write_text(json.dumps(dict(status='complete',seconds=time.monotonic()-started,dependencies=dependency_hashes()),indent=2)+'\n')
    print(json.dumps(dict(status='sensitivity complete',seconds=time.monotonic()-started,rows=len(rows))))


if __name__=='__main__': main()
