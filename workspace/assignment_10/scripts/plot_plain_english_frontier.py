"""Show the frozen delayed-loss comparison using portfolio counts and plain labels."""
from pathlib import Path
from hashlib import sha256
import json
import shutil

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
import pandas as pd

ROOT=Path(__file__).resolve().parents[1]
UNIVERSITY=Path('C:/Users/HP/Desktop/University/Working Manuscripts/Active Papers/Fund X Paper Review/Research/Assignment 10')
STEM='Return_Screening_Frontier_Explained'


def main():
    source=ROOT/'tables/frontier_curves_original.csv'
    data=pd.read_csv(source,float_precision='round_trip')
    data=data[(data.group=='all')&(data.mechanism=='relative_delay3')]
    old=data[data.policy=='OR:B+D'].sort_values('budget')
    new=data[data.policy=='OR:A+Z'].sort_values('budget')
    assert len(old)==len(new)==101
    assert old.n.eq(194).all() and new.n.eq(194).all()
    for rows in (old,new):
        assert rows.baseline.diff().dropna().ge(0).all()
        assert rows.altered.diff().dropna().ge(0).all()
        assert tuple(rows.iloc[0][['baseline','altered']])==(0,0)
        assert tuple(rows.iloc[-1][['baseline','altered']])==(194,194)
    assert tuple(old[old.budget.eq(.05)].iloc[0][['baseline','altered']])==(1,104)
    assert tuple(new[new.budget.eq(.05)].iloc[0][['baseline','altered']])==(3,192)
    matched=old[old.budget.eq(.07)].iloc[0]
    assert (matched.baseline,matched.altered)==(3,120)

    plt.rcParams.update({'font.family':'Times New Roman','font.size':13,
                         'axes.spines.top':False,'axes.spines.right':False,
                         'axes.labelsize':14,'svg.fonttype':'none'})
    fig=plt.figure(figsize=(12,7.2),facecolor='white')
    gs=fig.add_gridspec(1,2,width_ratios=[2.25,1],left=.085,right=.975,
                        bottom=.30,top=.79,wspace=.20)
    main_ax=fig.add_subplot(gs[0]);overview=fig.add_subplot(gs[1])
    fig.text(.085,.945,'Finding losses recorded three months late',
             fontsize=23,fontweight='bold',ha='left')
    fig.text(.085,.89,'194 published portfolios, each compared with a deliberately changed copy',
             fontsize=14,ha='left')
    for ax in (main_ax,overview):
        for rows,color,style in [(old,'0.48','--'),(new,'black','-')]:
            ax.step(rows.baseline,rows.altered,where='post',color=color,
                    linestyle=style,linewidth=2.2)
            ax.scatter(rows.baseline,rows.altered,s=10,color=color,zorder=3)
        ax.set_ylim(-2,201);ax.set_yticks([0,50,100,150,194])
        ax.grid(axis='y',alpha=.17)
        ax.set_xlabel('Untouched portfolios raising warnings',labelpad=9)
        ax.scatter([1],[104],s=70,color='0.48',edgecolors='white',zorder=5)
        ax.scatter([3],[192],s=70,color='black',edgecolors='white',zorder=5)
    main_ax.set_xlim(-.15,20.3);main_ax.set_xticks([0,5,10,15,20])
    main_ax.set_title('A closer look at the first 20 warnings',loc='left',fontsize=14,pad=12)
    main_ax.set_ylabel('Changed copies raising warnings',labelpad=10)
    overview.set_xlim(-2,196);overview.set_xticks([0,100,194])
    overview.set_title('Full range of warning levels',loc='left',fontsize=14,pad=12)
    overview.set_xlabel('Untouched portfolios\nraising warnings',labelpad=9)

    box=dict(boxstyle='round,pad=.28',fc='white',ec='none',alpha=.96)
    arrow=dict(arrowstyle='-',color='0.4',lw=.9,shrinkA=3,shrinkB=6)
    main_ax.annotate('192 caught; 3 untouched warned',xy=(3,192),xytext=(6.0,169),
                     fontsize=13,bbox=box,arrowprops=arrow,va='center')
    main_ax.annotate('104 caught; 1 untouched warned',xy=(1,104),xytext=(5.0,84),
                     fontsize=13,color='0.25',bbox=box,arrowprops=arrow,va='center')
    main_ax.scatter([3],[120],s=60,facecolors='white',edgecolors='0.48',linewidth=1.4,zorder=5)
    main_ax.annotate('Original pair at 3 warnings: 120 caught',xy=(3,120),xytext=(5.0,111),
                     fontsize=12,color='0.25',bbox=box,arrowprops=arrow,va='center')
    handles=[Line2D([0],[0],color='black',lw=2.2,
                    label='New pair: gains clustered just above zero + linked returns across months'),
             Line2D([0],[0],color='0.48',lw=2.2,ls='--',
                    label='Original pair: small-gain/loss balance + number of losing months')]
    fig.legend(handles=handles,loc='lower left',bbox_to_anchor=(.075,.125),
               frameon=False,ncol=1,fontsize=13,handlelength=3,labelspacing=.55)
    fig.text(.085,.092,'Higher = more reporting changes caught. Further left = fewer untouched portfolios sent for review.',
             fontsize=12,ha='left')
    fig.text(.085,.025,'Large filled dots mark the 5% allowance set on older data; the hollow dot matches the later warning count.\n'
             'Smaller dots show the other warning levels. Every cutoff setting is retained.',
             fontsize=11,ha='left',linespacing=1.25)
    paths=[]
    for ext in ['png','svg']:
        destination=ROOT/'figures'/f'{STEM}.{ext}'
        fig.savefig(destination,dpi=180,facecolor='white')
        target=UNIVERSITY/'figures'/destination.name
        target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(destination,target)
        assert destination.read_bytes()==target.read_bytes()
        paths.append(dict(file='figures/'+destination.name,sha256=sha256(destination.read_bytes()).hexdigest()))
    plt.close(fig)
    meta=dict(source='tables/frontier_curves_original.csv',source_sha256=sha256(source.read_bytes()).hexdigest(),
              cohort=194,window='2017-01 to 2025-12',reporting_change='Small losses replaced by small gains, with recognition three months later; quarter-SD eligibility bound',
              policies=['OR:B+D','OR:A+Z'],points_in_each_curve=101,
              axes=dict(x='Untouched portfolios raising warnings',y='Changed copies raising warnings'),
              plotted_cutoff_order='Older-calibration allowance increasing; every observed coordinate retained',
              highlighted_points=[dict(policy='OR:B+D',older_allowance=.05,x=1,y=104),dict(policy='OR:A+Z',older_allowance=.05,x=3,y=192),dict(policy='OR:B+D',older_allowance=.07,x=3,y=120)],
              interpretation='The matched later warning count is a descriptive comparison on this observed panel.',files=paths)
    (ROOT/'data/plain_english_frontier_metadata.json').write_text(json.dumps(meta,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(dict(figure=str(ROOT/'figures'/f'{STEM}.png'),source_sha256=meta['source_sha256'],verified_points=3,curves=2),indent=2))


if __name__=='__main__':main()
