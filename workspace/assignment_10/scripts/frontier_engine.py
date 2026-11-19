"""Frozen-data computation shared by the frontier runners."""
from hashlib import sha256
from io import StringIO
from pathlib import Path
import json

import numpy as np
import pandas as pd

from frontier_metrics import raw_scores,fit_maps,rank_scores,fit_pca,combine_scores,conservative_cutoffs

ROOT=Path(__file__).resolve().parents[1]


def design():
    return json.loads((ROOT/'data/frozen_design.json').read_text())


def inputs(weighting='original',names=None):
    if weighting=='original':
        frame=pd.read_parquet(ROOT/'data/raw/PredictorLSretWide.parquet')
        frame.index=pd.to_datetime(frame.pop('date')).dt.to_period('M')
    elif weighting=='value_weighted':
        data=pd.read_parquet(ROOT/'data/raw/PredictorVWforce.parquet')
        data=data[data.port.eq('LS')].copy()
        data['month']=pd.to_datetime(data.date).dt.to_period('M')
        frame=data.pivot(index='month',columns='signalname',values='ret')
    else:
        raise ValueError(weighting)
    if frame.index.has_duplicates:
        raise ValueError('Duplicate source month')
    frame=frame.sort_index().astype(float)/100
    if names is not None:
        frame=frame.loc[:,names]
    rows=[]
    for line in (ROOT/'data/raw/F-F_Research_Data_Factors.csv').read_text().splitlines():
        first=line.split(',')[0].strip()
        if len(first)==6 and first.isdigit(): rows.append(line)
    factors=pd.read_csv(StringIO('date,MKT,SMB,HML,RF\n'+'\n'.join(rows)))
    factors.index=pd.PeriodIndex(factors.pop('date').astype(str),freq='M')
    return frame,factors.RF.astype(float)/100


def calendar_indices(rng,draws,length,source_length,block):
    nblock=(length+block-1)//block
    starts=rng.integers(0,source_length,size=(draws,nblock))
    return ((starts[:,:,None]+np.arange(block))%source_length).reshape(draws,-1)[:,:length]


def dependency_hashes():
    files=['data/frozen_design.json','scripts/frontier_metrics.py','scripts/frontier_engine.py',
           'data/raw/PredictorLSretWide.parquet','data/raw/PredictorVWforce.parquet',
           'data/raw/F-F_Research_Data_Factors.csv','data/raw/SignalDoc.csv']
    return {p:sha256((ROOT/p).read_bytes()).hexdigest() for p in files}


def get_maps(panel,rf,length,representation,period,bandwidth=.25):
    observed=panel.loc[period[0]:period[1]]
    pieces=[];records=[]
    for end in range(length-1,len(observed)):
        if observed.index[end].month!=12: continue
        window=observed.iloc[end-length+1:end+1]
        good=window.notna().all()
        if not good.any(): continue
        values=window.loc[:,good].to_numpy().T
        if representation=='funded':
            values=values+rf.reindex(window.index).to_numpy()[None,:]
        scores,_=raw_scores(values,bandwidth)
        pieces.append(scores)
        records.append(dict(end=str(window.index[-1]),paths=int(good.sum())))
    if not pieces: raise ValueError('No development windows')
    scores=np.concatenate(pieces)
    return fit_maps(scores),dict(records=len(scores),endpoints=records)


def score_pack(panel,rf,length,block,draws,maps,representation,period,stage,bandwidth=.25):
    source=panel.loc[period[0]:period[1]]
    if source.isna().any().any(): raise ValueError('Calibration reference must be complete')
    cash=rf.reindex(source.index).to_numpy()
    if not np.isfinite(cash).all(): raise ValueError('Missing cash')
    rng=np.random.default_rng(np.random.SeedSequence([design()['seed'],stage,length,block]))
    out=np.empty((draws,len(source.columns),4))
    ranks=np.empty_like(out);h=np.empty(out.shape[:-1])
    for start in range(0,draws,25):
        stop=min(start+25,draws)
        ix=calendar_indices(rng,stop-start,length,len(source),block)
        values=source.to_numpy()[ix].transpose(0,2,1)
        h[start:stop]=values.mean(axis=-1)/values.std(axis=-1,ddof=1)
        if representation=='funded': values=values+cash[ix][:,None,:]
        raw,_=raw_scores(values,bandwidth)
        out[start:stop]=raw;ranks[start:stop]=rank_scores(raw,maps)
    return dict(raw=out,ranks=ranks,h=h)


def fit_reference(panel,rf,length,block,draws,representation,periods,namespace,bandwidth=.25):
    folder=ROOT/'data/cache';folder.mkdir(exist_ok=True)
    path=folder/(namespace+'.npz');meta_path=folder/(namespace+'.json')
    expected=dict(dependencies=dependency_hashes(),names=list(panel.columns),months=length,block=block,
                  draws=draws,representation=representation,periods=periods,bandwidth=bandwidth)
    if path.exists():
        meta=json.loads(meta_path.read_text())
        if meta['settings']!=expected: raise RuntimeError('Changed frozen cache settings: '+namespace)
        with np.load(path) as saved:
            return dict(maps=[saved[f'map{j}'].copy() for j in range(4)],
                        pca=meta['pca'],cutoffs=saved['cutoffs'].copy(),calibration_rates=saved['calibration_rates'].copy(),
                        raw=saved['raw'].copy(),ranks=saved['ranks'].copy(),h=saved['h'].copy(),map_metadata=meta['map_metadata'])
    maps,map_metadata=get_maps(panel,rf,length,representation,periods['development'],bandwidth)
    pack=score_pack(panel,rf,length,block,draws,maps,representation,periods['calibration'],1,bandwidth)
    pca=fit_pca(pack['ranks'])
    scores=combine_scores(pack['ranks'],design()['policies'],pca)
    cutoffs=np.stack([conservative_cutoffs(scores[...,j],design()['budgets']) for j in range(scores.shape[-1])])
    rates=np.stack([(scores[...,j].size-np.searchsorted(np.sort(scores[...,j].ravel()),cutoffs[j],side='right'))/scores[...,j].size
                    for j in range(scores.shape[-1])])
    budgets=np.asarray(design()['budgets'])
    if np.any(rates>budgets[None,:]+1e-12): raise ArithmeticError('Calibration budget exceeded')
    meta=dict(settings=expected,pca=pca,map_metadata=map_metadata)
    np.savez_compressed(path,**{f'map{j}':maps[j] for j in range(4)},cutoffs=cutoffs,calibration_rates=rates,**pack)
    meta_path.write_text(json.dumps(meta,indent=2)+'\n')
    return dict(maps=maps,pca=pca,cutoffs=cutoffs,calibration_rates=rates,map_metadata=map_metadata,**pack)


def apply_policy(full,policy,months,warmup=6,picks=None,funded=False):
    """Maintain a reconciled payoff/logNAV gap; only central months are screened."""
    x=np.asarray(full,dtype=float)
    stop=warmup+months
    original=x[...,warmup:stop]
    if policy['kind']=='smoothing':
        lam=policy['weight']
        altered=(1-lam)*original+lam*x[...,warmup-1:stop-1]
        error=float(np.max(np.abs((altered-original).sum(axis=-1)-lam*(x[...,warmup-1]-x[...,stop-1]))))
        return altered,np.any(np.abs(altered-original)>1e-14,axis=-1),dict(max_error=error,closing_gap=None)
    sd=original.std(axis=-1,ddof=1)
    bound=policy['bound']*(sd if policy['scale']=='sd' else np.ones_like(sd))
    gain=policy['gain']*(sd if policy['scale']=='sd' else np.ones_like(sd))
    eligible=(x>=-bound[...,None])&(x<0)
    eligible[...,stop:]=False
    if policy['p']<1:
        if picks is None: raise ValueError('Shared deterministic policy picks required')
        eligible&=picks<policy['p']
    if funded:
        if np.any(x<=-1): raise ValueError('Funded NAV support violation')
        coordinate=np.log1p(x);target=np.log1p(gain)
    else:
        coordinate=x;target=gain
    hidden=np.where(eligible,target[...,None]-coordinate,0)
    reported=coordinate+hidden
    lag=policy['lag']
    if lag!='permanent': reported[...,lag:]-=hidden[...,:-lag]
    opening=hidden[...,:warmup].sum(axis=-1) if lag=='permanent' else hidden[...,max(0,warmup-lag):warmup].sum(axis=-1)
    closing=hidden[...,:stop].sum(axis=-1) if lag=='permanent' else hidden[...,max(0,stop-lag):stop].sum(axis=-1)
    difference=(reported[...,warmup:stop]-coordinate[...,warmup:stop]).sum(axis=-1)
    error=float(np.max(np.abs(difference-(closing-opening))))
    if error>1e-11: raise ArithmeticError('Reporting ledger fails')
    altered=reported[...,warmup:stop]
    if funded: altered=np.expm1(altered)
    return altered,np.any(np.abs(altered-original)>1e-14,axis=-1),dict(max_error=error,closing_gap=float(np.mean(closing)))


def policy_training(panel,rf,reference,length,representation,period,draws,block=12):
    source=panel.loc[period[0]:period[1]]
    cash=rf.reindex(source.index).to_numpy()
    d=design();budgets=d['headline_budgets'];indices=[int(round(100*b)) for b in budgets]
    cut=reference['cutoffs'][:,indices]
    measures={};rng=np.random.default_rng(np.random.SeedSequence([d['seed'],2,length,block]))
    for start in range(0,draws,25):
        n=min(25,draws-start)
        ix=calendar_indices(rng,n,length,len(source),block)
        warmup=(ix[:,:1]+np.arange(-6,0)[None,:])%len(source)
        ix=np.concatenate([warmup,ix],axis=1)
        full=source.to_numpy()[ix].transpose(0,2,1)
        if representation=='funded': full=full+cash[ix][:,None,:]
        baseline=combine_scores(rank_scores(raw_scores(full[...,6:])[0],reference['maps']),d['policies'],reference['pca'])
        baseflag=baseline[...,None]>cut[None,None,:,:]
        for policy in d['reporting_policies']:
            if policy['id'] not in d['training_mechanisms']: continue
            altered,changed,_=apply_policy(full,policy,length,funded=representation=='funded')
            values=combine_scores(rank_scores(raw_scores(altered)[0],reference['maps']),d['policies'],reference['pca'])
            new=(values[...,None]>cut[None,None,:,:])&~baseflag
            measures.setdefault(policy['id'],[]).append(new.mean(axis=1))
    rates={name:np.concatenate(values).mean(axis=0) for name,values in measures.items()}
    choices=[]
    specs=d['policies']
    for leave in [None]+d['training_mechanisms']:
        objective=np.mean([rate for name,rate in rates.items() if name!=leave],axis=0)
        for group in ['all','primary',1,2,3,4]:
            eligible=[i for i,s in enumerate(specs) if group=='all' or (group=='primary' and s['primary']) or (isinstance(group,int) and s['count']==group)]
            for bidx,budget in enumerate(budgets):
                best=min(eligible,key=lambda i:(-objective[i,bidx],specs[i]['count'],specs[i]['id']))
                choices.append(dict(scope=str(group),left_out=leave or 'none',budget=budget,policy=specs[best]['id'],
                                    policy_index=best,families=specs[best]['count'],training_new_warning_rate=float(objective[best,bidx])))
    return rates,choices


def observed_window(panel,rf,end,length,representation):
    end=pd.Period(end,freq='M');start=end-length+1
    source=panel.loc[start-6:end]
    if len(source)!=length+6 or source.isna().any().any(): raise ValueError('Incomplete observed window')
    full=source.to_numpy().T
    raw=full[:,6:]
    h=raw.mean(axis=-1)/raw.std(axis=-1,ddof=1)
    if representation=='funded': full=full+rf.reindex(source.index).to_numpy()[None,:]
    return full,h


def performance_groups(h):
    n=len(h);count=int(np.ceil(n/5))
    rank=np.argsort(-h,kind='stable');high=np.zeros(n,dtype=bool);high[rank[:count]]=True
    return dict(all=np.ones(n,dtype=bool),top_quintile=high,remaining=~high)


def warning_statistics(base,scores,changed,cutoffs,budget_indices,groups):
    rows=[];specs=design()['policies'];budgets=design()['budgets']
    for group,mask in groups.items():
        b=base[mask];s=scores[mask];c=changed[mask];n=int(mask.sum())
        for j,spec in enumerate(specs):
            for bidx in budget_indices:
                before=b[:,j]>cutoffs[j,bidx];after=s[:,j]>cutoffs[j,bidx]
                rows.append(dict(group=group,n=n,changed=int(c.sum()),policy=spec['id'],families=spec['count'],primary=spec['primary'],
                    budget=float(budgets[bidx]),cutoff=float(cutoffs[j,bidx]),baseline=int(before.sum()),altered=int(after.sum()),
                    new=int((after&~before).sum()),cleared=int((before&~after).sum()),
                    baseline_rate=float(before.mean()),altered_rate=float(after.mean()),new_rate=float((after&~before).mean()),
                    changed_altered_rate=float(after[c].mean()) if c.any() else np.nan))
    return rows
