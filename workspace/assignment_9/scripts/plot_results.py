"""Scientific figures for the completed observed-return analysis."""
import json

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from a9_data import ROOT, phase_arrays
from a9_metrics import raw_scores, winner_weights


def main():
    plt.rcParams.update({'font.family':'Times New Roman','font.size':11,
                         'axes.spines.top':False,'axes.spines.right':False,
                         'savefig.dpi':180,'figure.dpi':120})
    folder=ROOT/'figures'
    folder.mkdir(exist_ok=True)
    desc=pd.read_csv(ROOT/'tables/descriptive_statistics.csv')
    fund=desc[(desc.signal=='Fund X')&(desc.months==108)].iloc[0]
    fig,ax=plt.subplots(figsize=(8,3.2))
    bins=np.linspace(-.35,.85,31)
    for weighting,label,style in [('original','Original construction','-'),('value_weighted','Forced value weighting','--')]:
        cohort=desc[(desc.weighting==weighting)&(desc.representation=='spread')]
        ax.hist(cohort.excess_sharpe,bins=bins,histtype='step',color='black',linestyle=style,label=f'{label} (195)')
    ax.axvline(fund.excess_sharpe,color='black',linewidth=1.2)
    ax.text(fund.excess_sharpe-.015,ax.get_ylim()[1]*.92,'Fund X',ha='right')
    ax.set(xlabel='Monthly excess-return Sharpe',ylabel='Number of strategies')
    ax.legend(frameon=False,loc='upper left')
    fig.tight_layout()
    fig.savefig(folder/'performance_support.png')
    plt.close(fig)

    curves=[]
    fig,axes=plt.subplots(1,2,figsize=(9,3.4),sharey=True)
    styles={'original':('black','-'),'value_weighted':('0.5','--')}
    for axis,length in zip(axes,[108,60]):
        for weighting in ['original','value_weighted']:
            frame,rf=phase_arrays(weighting,'evaluation')
            raw=frame.iloc[-length:].to_numpy().T
            cash=rf.iloc[-length:].to_numpy()
            h=raw.mean(axis=1)/raw.std(axis=1,ddof=1)
            order=np.argsort(-h,kind='stable')
            n=len(order)
            for kind in ['spread','funded']:
                values=raw if kind=='spread' else raw+cash[None,:]
                point=raw_scores(values)
                alert=(point['B']>2)|(point['normal_p']<.05)
                rates=[]
                for k in range(1,n+1):
                    rate=float(alert[order]@winner_weights(n,k))
                    rates.append(rate)
                    curves.append(dict(weighting=weighting,representation=kind,months=length,K=k,rate=rate))
                color,style=styles[weighting]
                axis.plot(range(1,n+1),100*np.array(rates),color=color,
                          linestyle=style if kind=='spread' else ':',
                          linewidth=1.5 if kind=='spread' else 1.,
                          label=f'{"Original" if weighting=="original" else "Value weighted"} {kind}')
        axis.set(title=f'{length} months ending December 2025',xlabel='Number of candidates K')
    axes[0].set_ylabel('Selected record warned (%)')
    axes[1].legend(frameon=False,fontsize=8)
    fig.tight_layout()
    fig.savefig(folder/'selection_curves.png')
    plt.close(fig)
    pd.DataFrame(curves).to_csv(ROOT/'tables/selection_curves.csv',index=False)

    point=pd.read_csv(ROOT/'tables/reporting_point.csv')
    case=point[(point.weighting=='original')&(point.representation=='spread')&(point.months==108)
               &(point.delta==.01)&(point.probability==1)]
    methods=['conventional_any','ordinary_calibrated','selection_calibrated']
    labels=['Conventional','Ordinary reference','Selection reference']
    lags=['permanent','1','3','6']
    fig,ax=plt.subplots(figsize=(8,3.4))
    positions=np.arange(5)
    for j,(method,label,color) in enumerate(zip(methods,labels,['0.15','0.55','0.85'])):
        rows=case[case.method==method]
        values=[float(rows.baseline_rate.iloc[0])]+[float(rows[rows.lag==lag].altered_rate.iloc[0]) for lag in lags]
        ax.bar(positions+(j-1)*.24,100*np.array(values),width=.23,color=color,edgecolor='black',linewidth=.5,label=label)
    ax.set_xticks(positions,['Unmodified','Permanent','1 month','3 months','6 months'])
    ax.set(ylabel='Records warned (%)',ylim=(0,100),xlabel='Recognition of eligible losses')
    ax.legend(frameon=False,fontsize=9)
    fig.tight_layout()
    fig.savefig(folder/'reporting_tradeoff.png')
    plt.close(fig)
    (ROOT/'data/figure_metadata.json').write_text(json.dumps(dict(
        font='Times New Roman',colors='black and grey',figures=[p.name for p in sorted(folder.glob('*.png'))],
        support_cohort=195,selection_and_reporting_cohort=194,
        selection_curve='Exact conditional subset probabilities for each integer K; no strategy-independence assumption',
        reporting='Fixed0.05% replacement gain, all underlying losses of at most1% in magnitude; actual108-month histories'),indent=2)+'\n')
    print('Three figures and exact selection-curve table written.')


if __name__=='__main__':
    main()
