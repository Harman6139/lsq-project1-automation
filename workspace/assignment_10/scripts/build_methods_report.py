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


def conversational_graph():
    source=ROOT/'tables/frontier_curves_original.csv'
    data=pd.read_csv(source,float_precision='round_trip')
    data=data[(data.group=='all')&(data.mechanism=='relative_delay3')]
    plt.rcParams.update({'font.family':'Times New Roman','font.size':10,
                         'axes.spines.top':False,'axes.spines.right':False,'svg.fonttype':'none'})
    fig,ax=plt.subplots(figsize=(7.1,3.2))
    fig.subplots_adjust(left=.10,right=.985,top=.88,bottom=.27)
    for policy,label,color,style in [('OR:A+Z','Checks 3+4','black','-'),('OR:B+D','Checks 1+2','0.48','--')]:
        rows=data[data.policy==policy].sort_values('budget')
        assert len(rows)==101
        ax.step(rows.baseline,rows.altered,where='post',label=label,color=color,linestyle=style,linewidth=1.7)
        ax.scatter(rows.baseline,rows.altered,color=color,s=9,zorder=3)
    for x,y,label,xy,color,hollow in [(3,192,'192 at 3 warnings',(7,170),'black',False),(1,104,'104 at 1 warning',(7,78),'0.35',False),(3,120,'120 at 3 warnings',(7,116),'0.35',True)]:
        ax.scatter([x],[y],s=35,facecolor='white' if hollow else color,edgecolor=color,zorder=5)
        ax.annotate(label,(x,y),xytext=xy,fontsize=10,color=color,
                    bbox=dict(fc='white',ec='none',pad=1),arrowprops=dict(arrowstyle='-',color='0.5',lw=.7))
    ax.set(xlim=(-.15,20.3),ylim=(-2,202),xticks=[0,5,10,15,20],yticks=[0,50,100,150,194])
    ax.set_title('Small losses recognised three months later',fontsize=11,pad=8)
    ax.set_xlabel('Untouched portfolios raising warnings',fontsize=10,labelpad=5)
    ax.set_ylabel('Changed copies raising warnings',fontsize=10,labelpad=6)
    ax.grid(axis='y',alpha=.16)
    fig.legend(*ax.get_legend_handles_labels(),loc='lower center',ncol=2,frameon=False,fontsize=10,bbox_to_anchor=(.55,.005))
    files=[]
    for ext in ['png','svg']:
        out=ROOT/'figures'/f'conversational_frontier.{ext}';fig.savefig(out,dpi=220,facecolor='white')
        files.append(dict(file='figures/'+out.name,sha256=sha256(out.read_bytes()).hexdigest()))
    plt.close(fig)
    meta=dict(source='tables/frontier_curves_original.csv',source_sha256=sha256(source.read_bytes()).hexdigest(),cohort=194,mechanism='relative_delay3',all_101_points_retained=True,shown_x_range=[0,20],marked_points=[[1,104],[3,192],[3,120]],files=files)
    (ROOT/'data/conversational_graph_metadata.json').write_text(json.dumps(meta,indent=2)+'\n',encoding='utf-8')


def main():
    conversational_graph()
    counts=pd.read_csv(ROOT/'tables/point_rates_original.csv',float_precision='round_trip')
    counts=counts[(counts.representation=='spread')&(counts.months==108)&(counts.end=='2025-12')&(counts.group=='all')&(counts.budget==.05)]
    lines=[]
    policies=[('OR:B+D','1+2 (original)'),('OR:A+Z','3+4'),('OR:B+A+Z','1+3+4'),('OR:B+D+A+Z','1+2+3+4')]
    for policy,label in policies:
        cells=[]
        for mechanism in ['unmodified','relative_delay3','smooth50']:
            row=counts[(counts.policy==policy)&(counts.mechanism==mechanism)].iloc[0]
            assert row.n==194
            cells.append(str(int(row.altered)))
        lines.append(label+' & '+' & '.join(cells)+r'\\')
    choice=pd.read_csv(ROOT/'tables/policy_choices_original.csv',float_precision='round_trip')
    choice=choice[(choice.representation=='spread')&(choice.months==108)&(choice.budget==.05)&(choice.left_out=='none')]
    assert choice[choice.scope=='all'].iloc[0].policy=='OR:B+A+Z'
    assert choice[choice.scope=='2'].iloc[0].policy=='OR:A+Z'
    text=(Path(__file__).with_name('methods_note_body.tex')).read_text(encoding='utf-8').replace('@@TABLE@@','\n'.join(lines))
    (ROOT/f'{STEM}.tex').write_text(text,encoding='utf-8')
    print(json.dumps(dict(source=str(ROOT/f'{STEM}.tex'),graphs=1,requested_pages='2-3',numerical_results='unchanged'),indent=2))


if __name__=='__main__':main()
