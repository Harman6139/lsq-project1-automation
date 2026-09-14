"""Reproducible review of the supplied two-regime note. Returns are decimals.

Run with Python 3.11+, numpy, pandas, scipy, numba, statsmodels, matplotlib.
All comparisons use the density of y=log(1+r), not the density of r.
No estimates in the original Word document are overwritten.
"""
from pathlib import Path
import sys, json, hashlib, warnings, argparse
ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parents[1]
local_deps = REPO / '.qa_assignment7/pythondeps'
if local_deps.exists(): sys.path.insert(0, str(local_deps))
import numpy as np
import pandas as pd
from scipy.optimize import minimize
from scipy.special import expit, logit
from scipy.stats import norm
from numba import njit
from statsmodels.tsa.stattools import acf
from statsmodels.stats.diagnostic import acorr_ljungbox
from statsmodels.tsa.regime_switching.markov_regression import MarkovRegression

SEED = 20260914

@njit
def forward(y, mu, sd, P, pi):
    n = len(y)
    filt = np.zeros((n, 2)); pred = np.zeros((n,2)); llobs = np.zeros(n)
    prior = pi.copy()
    for t in range(n):
        pred[t] = prior
        a = np.ones(2) if np.isnan(y[t]) else np.exp(-.5*((y[t]-mu)/sd)**2)/(np.sqrt(2*np.pi)*sd)
        w = a*prior; c = max(w.sum(), 1e-300)
        filt[t] = w/c; llobs[t] = np.log(c)
        prior = filt[t] @ P
    return llobs, filt, pred

@njit
def em(y, mu, sd, P, pi, mode, floor, maxiter=500):
    # mode 0 = stationary initial probability, 1 = estimated, 2 = fixed.
    # In mode 0 this supplies starting values; direct maximization follows.
    n=len(y); old=-1e300; observed=np.isfinite(y); clean=np.where(observed,y,0.)
    for iteration in range(maxiter):
        if mode == 0:
            pi=np.array([P[1,0],P[0,1]])/(P[1,0]+P[0,1])
        ls,filt,pred=forward(y,mu,sd,P,pi)
        ll=ls.sum()
        gam=np.zeros((n,2));gam[-1]=filt[-1]
        xis=np.zeros((2,2))
        for t in range(n-2,-1,-1):
            for i in range(2):
                for j in range(2):
                    v=filt[t,i]*P[i,j]*gam[t+1,j]/max(pred[t+1,j],1e-300)
                    gam[t,i]+=v; xis[i,j]+=v
        if abs(ll-old)<1e-9: break
        old=ll
        for i in range(2):
            weights=gam[:,i]*observed
            den=max(weights.sum(),1e-12)
            mu[i]=(weights*clean).sum()/den
            sd[i]=max(np.sqrt((weights*(clean-mu[i])**2).sum()/den),floor)
            P[i]=xis[i]/max(xis[i].sum(),1e-12)
            P[i]=np.maximum(P[i],1e-5);P[i]/=P[i].sum()
        if mode==1: pi=np.maximum(gam[0],1e-8);pi/=pi.sum()
    return mu,sd,P,pi,ll,iteration

def unpack(z,mode=0):
    mu=z[:2];sd=np.exp(z[2:4]);p=expit(z[4:6])
    P=np.array([[p[0],1-p[0]],[1-p[1],p[1]]])
    pi=np.array([P[1,0],P[0,1]])/(P[1,0]+P[0,1])
    if mode==1: pi=np.array([expit(z[6]),1-expit(z[6])])
    if mode==2: pi=np.array([1.,0.])
    return mu,sd,P,pi

def canonical(f):
    order=np.argsort(f['mu'])
    f['mu']=f['mu'][order];f['sd']=f['sd'][order]
    f['P']=f['P'][order][:,order];f['pi']=f['pi'][order]
    return f

def fit_hmm(y,starts=30,mode=0,floor=.001,seed=SEED):
    rng=np.random.default_rng(seed); candidates=[]; obs=y[np.isfinite(y)]
    for j in range(starts):
        if j==0:
            mu=np.array([.0237,.0895]);sd=np.array([.0211,.0606]);P=np.array([[.9119,.0881],[.4711,.5289]])
        elif j==1:
            mu=np.quantile(obs,[.25,.7]);sd=np.array([np.std(obs)*.3,np.std(obs)])
            P=np.array([[.93,.07],[.07,.93]])
        else:
            mu=np.sort(rng.choice(obs,2,replace=False));sd=np.std(obs)*rng.uniform(.2,1.8,2)
            p=rng.uniform(.05,.98,2);P=np.array([[p[0],1-p[0]],[1-p[1],p[1]]])
        pi=np.array([1.,0.]) if mode==2 else np.array([.5,.5])
        mu,sd,P,pi,ll,it=em(y.copy(),mu,sd,P,pi,mode,floor)
        z=np.r_[mu,np.log(sd),logit(np.clip(np.diag(P),1e-5,1-1e-5))]
        if mode==1: z=np.r_[z,logit(np.clip(pi[0],1e-8,1-1e-8))]
        candidates.append((ll,z,it))
    candidates.sort(key=lambda a:-a[0]); seen=set(); solutions=[]
    for ll,z,it in candidates:
        key=round(ll,3)
        if key in seen:continue
        seen.add(key)
        bounds=[(-1,1)]*2+[(np.log(floor),0)]*2+[(-11.5,11.5)]*2
        if mode==1:bounds += [(-20,20)]
        opt=minimize(lambda v:-forward(y,*unpack(v,mode))[0].sum(),z,
                     method='L-BFGS-B',bounds=bounds,options={'ftol':1e-13,'gtol':1e-7,'maxiter':2000})
        mu,sd,P,pi=unpack(opt.x,mode)
        solutions.append(canonical(dict(ll=float(-opt.fun),mu=mu,sd=sd,P=P,pi=pi,
                                         converged=bool(opt.success),floor=floor,mode=mode)))
        if len(solutions)>=12:break
    best=max(solutions,key=lambda a:a['ll'])
    best['starts']=starts;best['basin_likelihoods']=[a['ll'] for a in solutions]
    return best

def fit_iid(y,starts=100,floor=.001):
    rng=np.random.default_rng(SEED);best=None
    for k in range(starts):
        mu=np.sort(rng.choice(y,2,replace=False)); sd=np.std(y)*rng.uniform(.2,1.5,2);w=np.array([.5,.5]);old=-np.inf
        for it in range(1000):
            a=norm.pdf(y[:,None],mu,sd)*w
            c=np.maximum(a.sum(1),1e-300);g=a/c[:,None];ll=np.log(c).sum()
            if abs(ll-old)<1e-10:break
            old=ll;w=g.mean(0);mu=(g*y[:,None]).sum(0)/g.sum(0)
            sd=np.maximum(np.sqrt((g*(y[:,None]-mu)**2).sum(0)/g.sum(0)),floor)
        f=canonical(dict(ll=float(ll),mu=mu,sd=sd,P=np.tile(w,(2,1)),pi=w,floor=floor,mode=0))
        if best is None or ll>best['ll']:best=f
    return best

def viterbi(y,f):
    mu,sd,P,pi=(f[k] for k in ['mu','sd','P','pi'])
    delta=norm.logpdf(y[0],mu,sd)+np.log(np.maximum(pi,1e-300));back=np.zeros((len(y),2),int)
    for t in range(1,len(y)):
        a=delta[:,None]+np.log(P);back[t]=a.argmax(0)
        delta=a.max(0)+norm.logpdf(y[t],mu,sd)
    path=np.zeros(len(y),int);path[-1]=delta.argmax()
    for t in range(len(y)-2,-1,-1):path[t]=back[t+1,path[t+1]]
    return path

def moments(f,n):
    mu,sd,P=(f[k] for k in ['mu','sd','P']);pi=np.array([P[1,0],P[0,1]])/(P[1,0]+P[0,1])
    means=np.expm1(mu+sd**2/2);vars=np.expm1(sd**2)*np.exp(2*mu+sd**2)
    avg=pi@means;var=pi@(vars+(means-avg)**2)
    rho=(pi@(means-avg)**2)/var*(P.trace()-1)
    loss=norm.cdf(-mu/sd)
    # Exact count distribution conditional on the specified fitted model, NOT
    # an exact composite-null goodness-of-fit p-value after parameter estimation.
    dist=np.zeros((n+1,2));dist[0]=f['pi']*(1-loss);dist[1]=f['pi']*loss
    for t in range(1,n):
        prior=dist@P;dist=prior*(1-loss);dist[1:]+=prior[:-1]*loss
    return dict(mean_returns=means,sd_returns=np.sqrt(vars),stationary=pi,
                durations=1/(1-np.diag(P)),expected_loss_months=n*(pi@loss),
                loss_probability=pi@loss,count_le_5_probability=dist[:6].sum(),
                model_rho1=rho,model_mean=avg,model_sd=np.sqrt(var))

def serial(x):
    ac=acf(x,nlags=12,fft=False)
    lb=acorr_ljungbox(x,lags=[1,6,12],return_df=True)
    return dict(acf=ac[1:],Q=lb.lb_stat.to_numpy(),naive_asymptotic_p=lb.lb_pvalue.to_numpy())

def diagnostics(y,f):
    ls,filtered,pred=forward(y,*(f[k] for k in ['mu','sd','P','pi']))
    pit=(pred*norm.cdf((y[:,None]-f['mu'])/f['sd'])).sum(1)
    innovations=norm.ppf(np.clip(pit,1e-9,1-1e-9))
    return serial(innovations),innovations,filtered,pred,pit

def simulate(f,n,rng):
    s=rng.choice(2,p=f['pi']);out=np.zeros(n)
    for t in range(n):
        out[t]=rng.normal(f['mu'][s],f['sd'][s]);s=rng.choice(2,p=f['P'][s])
    return out

def native(o):
    if isinstance(o,dict):return {k:native(v) for k,v in o.items()}
    if isinstance(o,(list,tuple)):return [native(v) for v in o]
    if isinstance(o,np.ndarray):return o.tolist()
    if isinstance(o,np.generic):return o.item()
    return o

def sensitivity_checks(y,df):
    sens=[]
    for name,yy,floor in [('Exclude estimated July',y[:-1],.001),('Paper sample to May',y[:-2],.001),('Half standard deviation floor',y,.0005),('Double standard deviation floor',y,.002)]:
        f=fit_hmm(yy,100,floor=floor);sens.append(dict(name=name,n=len(yy),fit=f,moments=moments(f,len(yy))))
    for lo,hi in [('2018-08','2018-10'),('2020-03','2020-07'),('2021-01','2021-02'),('2025-09','2025-10')]:
        # Missing emissions equal one, so P continues to propagate monthly.
        # This preserves calendar spacing rather than joining nonadjacent months.
        yy=y.copy();yy[df.date.between(lo,hi)]=np.nan;f=fit_hmm(yy,100)
        sens.append(dict(name=f'Hide {lo} to {hi}; calendar preserved',n=int(np.isfinite(yy).sum()),fit=f,moments=moments(f,len(yy))))
    return sens

def main():
    args=argparse.ArgumentParser();args.add_argument('--permutations',type=int,default=499);args.add_argument('--bootstrap',type=int,default=199);args.add_argument('--sensitivity-only',action='store_true')
    args=args.parse_args();df=pd.read_csv(ROOT/'data/fund_x_2017_01_to_2026_07.csv')
    dates=pd.period_range('2017-01','2026-07',freq='M').astype(str)
    assert list(df.date)==list(dates) and not df.isna().any().any()
    r=df.lsq_return.to_numpy();assert (r>-1).all();y=np.log1p(r);n=len(y)
    if args.sensitivity_only:
        target=ROOT/'assignment7_results.json';result=json.loads(target.read_text())
        assert abs(fit_hmm(y,30)['ll']-result['best']['ll'])<1e-7
        result['sensitivity']=native(sensitivity_checks(y,df))
        target.write_text(json.dumps(result,indent=2)+'\n')
        print('Updated sensitivity with calendar spacing preserved',flush=True);return
    print('Fitting 300 starts',flush=True)
    best=fit_hmm(y,300);iid=fit_iid(y);one=float(norm.logpdf(y,y.mean(),y.std()).sum())
    free=fit_hmm(y,100,mode=1)
    note=dict(mu=np.array([.0237,.0895]),sd=np.array([.0211,.0606]),P=np.array([[.9119,.0881],[.4711,.5289]]),pi=np.array([.842,.158]))
    note['ll']=float(forward(y,*(note[k] for k in ['mu','sd','P','pi']))[0].sum())
    note_fixed={**note,'pi':np.array([1.,0.])};note_fixed['ll']=float(forward(y,*(note_fixed[k] for k in ['mu','sd','P','pi']))[0].sum())
    # Independent library optimizer, using its own Hamilton filter and smoother.
    np.random.seed(SEED);mod=MarkovRegression(y,k_regimes=2,trend='c',switching_variance=True)
    with warnings.catch_warnings():
        warnings.simplefilter('ignore');ind=mod.fit(search_reps=100,search_iter=30,em_iter=50,maxiter=2000,disp=False)
    p=ind.params;indfit=canonical(dict(ll=ind.llf,mu=p[2:4].copy(),sd=np.sqrt(p[4:6]),P=np.array([[p[0],1-p[0]],[p[1],1-p[1]]]),pi=np.array([p[1],1-p[0]])/(p[1]+1-p[0])))
    assert abs(best['ll']-ind.llf)<1e-5,(best['ll'],ind.llf)
    print('Verified likelihood',best['ll'],'iid',iid['ll'],'note',note['ll'],'free',free['ll'],flush=True)
    models=[('One regime',2,one),('Independent mixture',5,iid['ll']),('Note rounded stationary',6,note['ll']),('Two regimes stationary',6,best['ll']),('Two regimes free initial',7,free['ll'])]
    comparison=pd.DataFrame([dict(model=a,parameters=k,log_likelihood=ll,AIC=-2*ll+2*k,BIC=-2*ll+k*np.log(n)) for a,k,ll in models])
    comparison.to_csv(ROOT/'tables/model_comparison.csv',index=False)
    d,innov,filtered,pred,pit=diagnostics(y,best);path=viterbi(y,best);note_path=viterbi(y,note_fixed)
    monthly=df.copy();monthly['log_return']=y;monthly['high_state_viterbi']=path;monthly['high_probability_filtered']=filtered[:,1];monthly['high_probability_predicted']=pred[:,1];monthly['forecast_pit']=pit;monthly['forecast_innovation']=innov;monthly['note_viterbi']=note_path
    monthly.to_csv(ROOT/'tables/monthly_model_results.csv',index=False)
    raw=serial(r);logs=serial(y);resid=serial(y-best['mu'][path]);note_resid=serial(y-note['mu'][note_path])
    data_info=dict(n=n,negative_count=int((r<0).sum()),zero_count=int((r==0).sum()),mean=r.mean(),sd=r.std(ddof=1),start=df.date.iloc[0],end=df.date.iloc[-1],ties=n-len(np.unique(r)),july_is_estimate=True)
    rng=np.random.default_rng(SEED+1);perm=[];observed=fit_hmm(y,20)['ll']-iid['ll']
    assert abs(observed-(best['ll']-iid['ll']))<1e-5
    for b in range(args.permutations):
        perm.append(fit_hmm(rng.permutation(y),20)['ll']-iid['ll'])
        if (b+1)%50==0:print('Ordering permutations',b+1,flush=True)
    perm=np.array(perm);permp=(1+sum(perm>=observed))/(len(perm)+1)
    pd.DataFrame({'gain_over_iid_mixture':perm}).to_csv(ROOT/'tables/ordering_permutations.csv',index=False)
    boot=[];rng=np.random.default_rng(SEED+2)
    for b in range(args.bootstrap):
        sim=simulate(best,n,rng);sf=fit_hmm(sim,20);sdg,*_=diagnostics(sim,sf)
        boot.append([sdg['Q'][2],(sim<0).sum()])
        if (b+1)%50==0:print('Refitted model simulations',b+1,flush=True)
    boot=np.array(boot);bootp=(1+sum(boot[:,0]>=d['Q'][2]))/(len(boot)+1)
    pd.DataFrame(boot,columns=['refitted_forecast_Q12','negative_months']).to_csv(ROOT/'tables/refit_bootstrap.csv',index=False)
    # Expanding one-month-ahead validation: forecasts use data only through t-1.
    holdout=[]
    for t in range(96,n):
        train=y[:t];hf=fit_hmm(train,40);mix=fit_iid(train,30)
        ls,ff,_=forward(train,*(hf[k] for k in ['mu','sd','P','pi']));pr=ff[-1]@hf['P']
        hm=np.expm1(hf['mu']+hf['sd']**2/2);im=np.expm1(mix['mu']+mix['sd']**2/2)
        scores=[norm.logpdf(y[t],train.mean(),train.std()),np.log(np.dot(mix['pi'],norm.pdf(y[t],mix['mu'],mix['sd']))),np.log(np.dot(pr,norm.pdf(y[t],hf['mu'],hf['sd'])))]
        forecasts=[np.expm1(train.mean()+train.var()/2),mix['pi']@im,pr@hm]
        holdout.append(dict(date=df.date.iloc[t],actual=r[t],one_log_score=scores[0],mixture_log_score=scores[1],hmm_log_score=scores[2],one_mean=forecasts[0],mixture_mean=forecasts[1],hmm_mean=forecasts[2]))
    h=pd.DataFrame(holdout);h.to_csv(ROOT/'tables/expanding_forecasts.csv',index=False)
    validation={a:dict(log_score=h[a+'_log_score'].sum(),rmse=np.sqrt(np.mean((h[a+'_mean']-h.actual)**2))) for a in ['one','mixture','hmm']}
    sens=sensitivity_checks(y,df)
    results=dict(data=data_info,best=best,best_moments=moments(best,n),independent_statsmodels=indfit,iid=iid,note_rounded=note,note_low_initial=note_fixed,note_moments=moments(note,n),free_initial=free,comparison=comparison.to_dict('records'),raw_diagnostics=raw,log_diagnostics=logs,viterbi_residual_diagnostics=resid,note_residual_diagnostics=note_resid,forecast_diagnostics=d,ordering_test=dict(null='Returns are exchangeable in time conditional on observed values',alternative='Large optimized HMM likelihood gain over iid mixture',gain=observed,reps=len(perm),exceedances=int(sum(perm>=observed)),p=permp,seed=SEED+1,starts_per_fit=20),forecast_Q12_bootstrap=dict(null='Fitted stationary two-regime Gaussian HMM on log returns',alternative='Large Q12 of normal-score predictive innovations',Q12=d['Q'][2],p=bootp,reps=len(boot),exceedances=int(sum(boot[:,0]>=d['Q'][2])),seed=SEED+2,refit=True),validation=validation,validation_months=len(h),sensitivity=sens,high_months=list(df.date[path==1]),note_high_months=list(df.date[note_path==1]))
    (ROOT/'assignment7_results.json').write_text(json.dumps(native(results),indent=2)+'\n',encoding='utf-8')
    print(json.dumps(native({k:results[k] for k in ['data','best_moments','ordering_test','forecast_Q12_bootstrap','validation']}),indent=2),flush=True)

if __name__=='__main__':main()
