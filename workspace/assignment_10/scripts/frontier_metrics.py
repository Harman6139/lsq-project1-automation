"""Four one-sided return diagnostics and fixed combinations, not fraud probabilities."""
from itertools import combinations

import numpy as np
from scipy.special import ndtr

FIELDS = ['B', 'D', 'A', 'Z']


def raw_scores(values, bandwidth=.25):
    x = np.asarray(values, dtype=np.float64)
    if x.ndim < 2 or x.shape[-1] < 4 or not np.isfinite(x).all():
        raise ValueError('Expected complete finite return paths in the last dimension')
    mean = x.mean(axis=-1)
    sd = x.std(axis=-1, ddof=1)
    if np.any(sd <= 0):
        raise ValueError('Nonpositive sample standard deviation')
    centered = x-mean[..., None]
    negative = (x < 0).sum(axis=-1)
    upper = ((x >= 0) & (x <= sd[..., None])).sum(axis=-1)
    lower = ((x < 0) & (x >= -sd[..., None])).sum(axis=-1)
    bias = upper/(1+lower)
    deficit = x.shape[-1]*ndtr(-mean/sd)-negative
    acf = (centered[..., 1:]*centered[..., :-1]).sum(axis=-1)/(centered*centered).sum(axis=-1)
    b = bandwidth*sd[..., None]
    l1 = ((x >= -b) & (x < 0)).sum(axis=-1)
    l2 = ((x >= -2*b) & (x < -b)).sum(axis=-1)
    g1 = ((x > 0) & (x <= b)).sum(axis=-1)
    g2 = ((x > b) & (x <= 2*b)).sum(axis=-1)
    denominator = np.sqrt(9*(g1+l1)+g2+l2)
    local = np.divide(3*(g1-l1)-(g2-l2), denominator,
                      out=np.zeros_like(mean), where=denominator > 0)
    scores = np.stack([bias, deficit, acf, local], axis=-1)
    details = dict(mean=mean, sd=sd, h=mean/sd, negative=negative,
                   upper=upper, lower=lower, exact_zeros=(x == 0).sum(axis=-1),
                   local_l1=l1, local_l2=l2, local_g1=g1, local_g2=g2)
    return scores, details


def fit_maps(scores):
    flat = np.asarray(scores, dtype=float).reshape(-1, 4)
    if not np.isfinite(flat).all() or not len(flat):
        raise ValueError('Invalid development scores')
    return [np.sort(flat[:, j]) for j in range(4)]


def rank_scores(scores, maps):
    values = np.asarray(scores, dtype=float)
    return np.stack([np.searchsorted(maps[j], values[..., j], side='right')/(len(maps[j])+1)
                     for j in range(4)], axis=-1)


def policy_specs(include_comparators=True):
    specs=[]
    for count in range(1, 5):
        for mask in combinations(range(4), count):
            fields='+'.join(FIELDS[i] for i in mask)
            specs.append(dict(id=fields if count==1 else 'OR:'+fields, indices=list(mask),
                              count=count, aggregation='any', primary=True))
            if count>1:
                specs.append(dict(id='MAJ:'+fields, indices=list(mask), count=count,
                                  aggregation='majority', primary=True))
                if include_comparators:
                    specs.append(dict(id='MEAN:'+fields, indices=list(mask), count=count,
                                      aggregation='mean', primary=False))
    if include_comparators:
        specs.append(dict(id='PCA:B+D+A+Z',indices=list(range(4)),count=4,
                          aggregation='pca',primary=False))
    return specs


def fit_pca(ranks):
    values=np.asarray(ranks).reshape(-1,4)
    mean=values.mean(axis=0)
    sd=values.std(axis=0,ddof=1)
    standardized=(values-mean)/sd
    _,vectors=np.linalg.eigh(np.cov(standardized,rowvar=False))
    weights=vectors[:,-1]
    if weights.sum()<0 or (weights.sum()==0 and weights[np.argmax(np.abs(weights))]<0):
        weights=-weights
    return dict(mean=mean.tolist(),sd=sd.tolist(),weights=weights.tolist())


def combine_scores(ranks, specs=None, pca=None):
    if specs is None:
        specs=policy_specs()
    values=np.asarray(ranks,dtype=float)
    out=[]
    for spec in specs:
        selected=values[...,spec['indices']]
        mode=spec['aggregation']
        if mode=='any':
            result=selected.max(axis=-1)
        elif mode=='majority':
            votes=spec['count']//2+1
            result=np.sort(selected,axis=-1)[...,-votes]
        elif mode=='mean':
            result=selected.mean(axis=-1)
        elif mode=='pca':
            if pca is None:
                raise ValueError('PCA parameters must be fitted using old data')
            result=((values-np.asarray(pca['mean']))/np.asarray(pca['sd']))@np.asarray(pca['weights'])
        else:
            raise ValueError(mode)
        out.append(result)
    return np.stack(out,axis=-1)


def conservative_cutoffs(values, budgets, weights=None):
    """Cutoffs with strict exceedance; ties are not randomly split."""
    scores=np.asarray(values,dtype=float).ravel()
    budgets=np.asarray(budgets,dtype=float)
    if weights is None:
        ordered=np.sort(scores)
        indices=np.ceil((1-budgets)*len(ordered)).astype(int)-1
        cutoffs=ordered[np.clip(indices,0,len(ordered)-1)].copy()
    else:
        weights=np.asarray(weights,dtype=float).ravel()
        if weights.shape!=scores.shape or np.any(weights<0) or weights.sum()<=0:
            raise ValueError('Invalid conditional selection weights')
        order=np.argsort(scores,kind='stable')
        cumulative=np.cumsum(weights[order])
        indices=np.searchsorted(cumulative,(1-budgets)*cumulative[-1],side='left')
        cutoffs=scores[order[np.clip(indices,0,len(order)-1)]].copy()
    cutoffs[budgets==0]=np.inf
    cutoffs[budgets==1]=-np.inf
    return cutoffs


def alert_rates(scores,cutoffs):
    """Return policy x budget rates over all leading path dimensions."""
    values=np.asarray(scores,dtype=float).reshape(-1,scores.shape[-1])
    return np.stack([(values[:,j,None]>cutoffs[j][None,:]).mean(axis=0)
                     for j in range(values.shape[1])])
