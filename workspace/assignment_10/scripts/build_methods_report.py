"""Build a colleague-facing methods note from the frozen frontier results."""
from hashlib import sha256
from pathlib import Path
import json

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

ROOT=Path(__file__).resolve().parents[1]
STEM='Return_Screening_Frontier'


def graphs():
    data=pd.read_csv(ROOT/'tables/frontier_curves_original.csv',float_precision='round_trip')
    data=data[data.group.eq('all')]
    plt.rcParams.update({'font.family':'Times New Roman','font.size':10,
                         'axes.spines.top':False,'axes.spines.right':False})
    configurations=[('Z','1: Z','0.6',':'),('OR:A+Z','2: A+Z','black','-'),
                    ('OR:B+A+Z','3: B+A+Z','0.3','--'),('OR:B+D+A+Z','4: B+D+A+Z','0.65','-.'),
                    ('OR:B+D','Original: B+D','0.4',(0,(1,3)))]
    files=[]
    for mechanism,title,filename in [
            ('relative_delay3','Small losses recognised three months later','report_loss_delay.png'),
            ('smooth50','Half current return plus half previous return','report_smoothing.png')]:
        fig,ax=plt.subplots(figsize=(6.8,2.2))
        fig.subplots_adjust(left=.095,right=.985,top=.85,bottom=.30)
        for policy,label,color,style in configurations:
            rows=data[(data.policy==policy)&(data.mechanism==mechanism)].sort_values('budget')
            # Plot every frozen cutoff in alpha order, retaining all vertical moves and the origin.
            ax.step(100*rows.baseline_rate,100*rows.altered_rate,where='post',
                    label=label,color=color,linestyle=style,linewidth=1.5)
            point=rows[rows.budget.eq(.05)].iloc[0]
            ax.scatter(100*point.baseline_rate,100*point.altered_rate,s=20,
                       facecolor=color,edgecolor='black',linewidth=.4,zorder=4)
        ax.scatter([0],[0],s=12,facecolor='white',edgecolor='black',linewidth=.6,zorder=5,clip_on=False)
        ax.set_xlim(0,12);ax.set_ylim(0,103);ax.set_yticks([0,25,50,75,100])
        ax.set_title(title,fontsize=11,pad=8)
        ax.set_xlabel('Unchanged records flagged (%)',labelpad=3)
        ax.set_ylabel('Altered records flagged (%)',labelpad=5)
        ax.grid(axis='y',alpha=.14)
        handles,labels=ax.get_legend_handles_labels()
        fig.legend(handles,labels,loc='lower center',ncol=5,frameon=False,
                   fontsize=9,bbox_to_anchor=(.53,.005),handlelength=2,columnspacing=1.1)
        destination=ROOT/'figures'/filename
        fig.savefig(destination,dpi=220,facecolor='white');plt.close(fig)
        files.append(dict(file='figures/'+filename,sha256=sha256(destination.read_bytes()).hexdigest()))
    meta=dict(source='tables/frontier_curves_original.csv',source_sha256=sha256((ROOT/'tables/frontier_curves_original.csv').read_bytes()).hexdigest(),
              group='all194',window='2017-01 to2025-12',configuration_choice='count-specific choices selected using old calibration data at5%; B+D is the prespecified comparator; IDs held fixed while alpha varies0..1 in.01 steps',
              plotted='actual later unchanged-warning rate versus total altered-warning rate',
              vertical_moves='all cutoffs retained in alpha order; no duplicate-x upper-bound collapse',files=files)
    (ROOT/'data/methods_graph_metadata.json').write_text(json.dumps(meta,indent=2)+'\n')


def main():
    graphs()
    counts=pd.read_csv(ROOT/'tables/handoff_comparison.csv')
    lines=[]
    for i,row in counts.iterrows():
        source='US' if row.source.startswith('US') else 'World'
        label={'unmodified':'Unchanged','relative_delay3':'Three-month delay','smooth50':'Half-weight smoothing'}[row.mechanism]
        lines.append(f'{source} & {label} & {row.n} & {row.old_pair_warnings} & {row.local_serial_pair_warnings} '+r'\\')
        if i==2:lines.append(r'\midrule')
    text=(Path(__file__).with_name('methods_note_body.tex')).read_text(encoding='utf-8').replace('@@TABLE@@','\n'.join(lines))
    (ROOT/f'{STEM}.tex').write_text(text,encoding='utf-8')
    print(json.dumps(dict(source=str(ROOT/f'{STEM}.tex'),graphs=2,requested_pages='2-3',numerical_results='unchanged'),indent=2))


if __name__=='__main__':main()
