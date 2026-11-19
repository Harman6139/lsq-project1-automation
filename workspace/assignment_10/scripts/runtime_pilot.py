"""Time the proposed calculations; discard all screening outcomes."""
from pathlib import Path
import itertools
import json
import sys
import time

import numpy as np
from scipy.special import ndtr

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT.parent / 'assignment_9/scripts'))
from a9_data import circular_indices, phase_arrays


def scores(x):
    mean = x.mean(axis=-1)
    sd = x.std(axis=-1, ddof=1)
    centered = x-mean[..., None]
    neg = (x < 0).sum(axis=-1)
    bias = ((x >= 0) & (x <= sd[..., None])).sum(axis=-1) / (1+((x < 0) & (x >= -sd[..., None])).sum(axis=-1))
    deficit = x.shape[-1]*ndtr(-mean/sd)-neg
    acf = (centered[..., 1:]*centered[..., :-1]).sum(axis=-1)/(centered*centered).sum(axis=-1)
    b = .25*sd[..., None]
    left1 = ((x >= -b) & (x < 0)).sum(axis=-1)
    left2 = ((x >= -2*b) & (x < -b)).sum(axis=-1)
    right1 = ((x > 0) & (x <= b)).sum(axis=-1)
    right2 = ((x > b) & (x <= 2*b)).sum(axis=-1)
    denom = np.sqrt(9*(right1+left1)+right2+left2)
    local = np.divide(3*(right1-left1)-(right2-left2),denom,out=np.zeros_like(mean),where=denom>0)
    return np.stack([bias, deficit, acf, local],axis=-1)


def main():
    frame, cash = phase_arrays('original','calibration')
    rng = np.random.default_rng(20261119)
    draws = 200
    ix = circular_indices(rng,draws,108,len(frame),12)
    start = time.perf_counter()
    x = frame.to_numpy()[ix].transpose(0,2,1)
    raw = scores(x)
    funded = scores(x+cash.to_numpy()[ix][:,None,:])
    score_seconds = time.perf_counter()-start
    start = time.perf_counter()
    policies=[]
    for count in range(1,5):
        for mask in itertools.combinations(range(4),count):
            policies.append(raw[...,mask].max(axis=-1))
            if count>1:
                policies.append(np.sort(raw[...,mask],axis=-1)[..., -(count//2+1)])
    for p in policies:
        np.quantile(p.ravel(),np.linspace(0,1,101))
    frontier_seconds = time.perf_counter()-start
    projected_score = score_seconds*340
    projected_frontier = frontier_seconds*160
    projected = 3*(projected_score+projected_frontier)+60
    result=dict(pilot_draws=draws,strategies=x.shape[1],months=108,
                score_seconds=score_seconds,frontier_seconds=frontier_seconds,
                policies=len(policies),conservative_projected_seconds=projected,
                projected_minutes=projected/60,
                cpu26_required_under_ten_minute_rule=projected>600,
                screening_outcomes='discarded; timing only, no outcome inspection',
                sink_shape=list(funded.shape))
    (ROOT/'data').mkdir(parents=True,exist_ok=True)
    (ROOT/'data/runtime_pilot.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result,indent=2))


if __name__=='__main__':
    main()
