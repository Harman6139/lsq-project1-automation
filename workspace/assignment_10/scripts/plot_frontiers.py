"""Scientific figure: actual later warning burden against total altered-record alerts."""
from pathlib import Path
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

ROOT=Path(__file__).resolve().parents[1]
plt.rcParams.update({'font.family':'Times New Roman','font.size':11,'axes.spines.top':False,'axes.spines.right':False})


def main():
    data=pd.read_csv(ROOT/'tables/frontier_curves_original.csv')
    data=data[data.group.eq('all')]
    specs=[('Z','One: local zero check','0.55',':'),('OR:A+Z','Two: local + serial','black','-'),
           ('OR:B+A+Z','Three: add bias ratio','0.3','--'),('OR:B+D+A+Z','Four checks','0.65','-.'),
           ('OR:B+D','Original pair','0.4',(0,(1,3)))]
    figure,axes=plt.subplots(1,2,figsize=(10.8,4),sharex=True,sharey=True)
    for ax,(mechanism,title) in zip(axes,[('relative_delay3','Small losses recognised 3 months later'),('smooth50','Half current + half previous return')]):
        for policy,label,color,style in specs:
            rows=data[(data.policy==policy)&(data.mechanism==mechanism)]
            # Highest attainable alert rate when several old cutoffs yield the same test burden.
            curve=rows.groupby('baseline_rate',as_index=False).altered_rate.max().sort_values('baseline_rate')
            ax.step([0]+list(100*curve.baseline_rate),[0]+list(100*curve.altered_rate),where='post',label=label,color=color,linestyle=style,linewidth=1.6)
            point=rows[rows.budget==.05].iloc[0]
            ax.scatter([100*point.baseline_rate],[100*point.altered_rate],s=20,facecolor=color,edgecolor='black',linewidth=.4,zorder=5)
        ax.set_title(title,fontsize=11,pad=10);ax.set_xlim(0,12);ax.set_ylim(0,103)
        ax.set_xlabel('Unchanged records warned (%)');ax.grid(axis='y',alpha=.15)
    axes[0].set_ylabel('Altered records warned (%)')
    handles,labels=axes[0].get_legend_handles_labels()
    figure.legend(handles,labels,loc='lower center',ncol=3,frameon=False,fontsize=10,bbox_to_anchor=(.5,-.07))
    figure.text(.5,-.115,'US histories, 2017-2025. Dots show the 5% older-reference allowance; curves vary the old cutoffs.',
                ha='center',va='center',fontsize=9)
    figure.tight_layout(rect=[0,.09,1,1])
    figure.savefig(ROOT/'figures/frontier_types_and_quantity.png',dpi=200,bbox_inches='tight',facecolor='white')
    plt.close(figure)


if __name__=='__main__': main()
