"""Render saved reporting comparisons; no calibration or simulation is run."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import subprocess

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages
from matplotlib import font_manager
import numpy as np
import pandas as pd
from pypdf import PdfReader

ROOT = Path(__file__).resolve().parents[1]
FIGURES = ROOT / 'figures'
PAGE_SIZE = (16.54, 11.69)  # A3 landscape, readable type for 38 complete rows.
MECHANISMS = [
    'relative_permanent', 'relative_delay1', 'relative_delay3',
    'relative_delay6', 'relative_half_delay3', 'fixed_permanent',
    'fixed_delay3', 'smooth25', 'smooth50', 'smooth75',
]
HEADERS = [
    'Small losses\nleft out', 'Small losses\n1-month delay',
    'Small losses\n3-month delay', 'Small losses\n6-month delay',
    'Half small losses\n3-month delay', 'Losses up to 1%\nleft out',
    'Losses up to 1%\n3-month delay', 'Averaging, 25%\nprevious month',
    'Averaging, 50%\nprevious month', 'Averaging, 75%\nprevious month',
]
TITLES = [
    'Small losses left out', 'Small losses delayed\n1 month',
    'Small losses delayed\n3 months', 'Small losses delayed\n6 months',
    'Half the small losses\ndelayed 3 months', 'Losses up to 1% left out',
    'Losses up to 1%\ndelayed 3 months', 'Averaging, 25%\nprevious month',
    'Averaging, 50%\nprevious month', 'Averaging, 75%\nprevious month',
]

def load(name):
    return pd.read_csv(ROOT/'tables'/name, float_precision='round_trip')

def setup_fonts():
    for filename in ['times.ttf', 'timesbd.ttf', 'timesi.ttf', 'timesbi.ttf']:
        font_manager.fontManager.addfont(str(Path('C:/Windows/Fonts')/filename))
    plt.rcParams.update({
        'font.family':'Times New Roman', 'font.size':12,
        'text.color':'black', 'axes.labelcolor':'black',
        'xtick.color':'black', 'ytick.color':'black',
        'pdf.fonttype':42, 'ps.fonttype':42,
        'axes.spines.top':False, 'axes.spines.right':False,
        'axes.edgecolor':'black', 'figure.facecolor':'white',
        'savefig.facecolor':'white',
    })

def short_rule(policy):
    if ':' not in policy:
        label = {'B':'B (small gains versus losses)','D':'D (too few losing months)',
                 'A':'A (consecutive months)','Z':'Z (tiny gains near zero)'}[policy]
    else:
        kind, fields = policy.split(':')
        fields=fields.split('+')
        if kind=='OR':
            label=' or '.join(fields)
        elif kind=='MAJ' and len(fields)==2:
            label=' and '.join(fields)
        elif kind=='MEAN' and len(fields)==2:
            label='Mean of '+' and '.join(fields)
        else:
            label={'MAJ':'Majority of ','MEAN':'Mean of ','PCA':'PC of '}[kind]+', '.join(fields)
    return label

def matrix_figure(data, design, value_field, baseline_field, title, subtitle, page,
                  group='all', difference=False):
    chosen=data[(data.group==group)&(data.budget==.05)]
    assert len(chosen)==380 and not chosen.duplicated(['policy','mechanism']).any()
    specs=design['policies'];policies=[x['id'] for x in specs]
    main=chosen.pivot(index='policy',columns='mechanism',values=value_field).loc[policies,MECHANISMS]
    baseline=chosen.groupby('policy')[baseline_field].agg(['min','max']).loc[policies]
    assert np.array_equal(baseline['min'],baseline['max'])
    values=np.column_stack([baseline['min'].to_numpy(),main.to_numpy()]).astype(int)
    assert values.shape==(38,11)
    n=194 if group=='all' else 39
    fig=plt.figure(figsize=PAGE_SIZE)
    fig.text(.035,.965,title,fontsize=22,fontweight='bold',va='top')
    fig.text(.035,.923,subtitle,fontsize=13,va='top')
    if difference:
        detail='Positive numbers mean more warnings than the named pair. Negative numbers mean fewer. The first column compares warnings on unchanged histories.'
    else:
        detail=f'Each cell counts all histories flagged in that version. The first column shows warnings on the unchanged histories out of {n}.'
    fig.text(.035,.895,detail,fontsize=12.5,va='top')
    ax=fig.add_axes([.205,.205,.76,.62])
    backgrounds=np.ones((38,11,3))
    for i,spec in enumerate(specs):
        backgrounds[i,:,:]=.974 if i%2 else 1.
        backgrounds[i,0,:]=.91
        if spec['id'] in ['OR:B+D','OR:A+Z']:
            backgrounds[i,:,:]=.915
            backgrounds[i,0,:]=.86
    ax.imshow(backgrounds,aspect='auto',interpolation='nearest',origin='upper')
    ax.set_xticks(range(11),(['Unchanged\ndifference'] if difference else ['Unchanged\nhistories'])+HEADERS)
    ax.tick_params(axis='x',top=True,bottom=False,labeltop=True,labelbottom=False,length=0,pad=10,labelsize=11.1)
    ax.set_yticks(range(38),[short_rule(s['id']) for s in specs])
    ax.tick_params(axis='y',length=0,pad=11,labelsize=11.3)
    for tick,spec in zip(ax.get_yticklabels(),specs):
        if spec['id'] in ['OR:B+D','OR:A+Z']:
            tick.set_fontweight('bold')
    column_max=values[:,1:].max(axis=0)
    for i in range(38):
        for j in range(11):
            value=int(values[i,j]);label=f'{value:+d}' if difference and value else str(value)
            weight='bold' if (j==0 or (j>0 and value==column_max[j-1])) else 'normal'
            ax.text(j,i,label,ha='center',va='center',fontsize=10.7,fontweight=weight,color='black')
    for i in [3.5,21.5,33.5]:
        ax.axhline(i,color='.62',linewidth=.6)
    ax.axvline(.5,color='.45',linewidth=.7)
    ax.set_xlim(-.5,10.5);ax.set_ylim(37.5,-.5)
    for spine in ax.spines.values():
        spine.set_visible(False)
    footer=[
        'B compares small gains and losses. D asks whether a bell curve would predict more losing months.',
        'A measures links between consecutive months. Z looks for gains piling up just above zero.',
        'Each rule gets one cutoff. Or means any check is high. And requires both. Majority requires more than half. Mean averages ranks. PC uses a weighted score.',
        'We replace losses of up to a quarter of a monthly standard deviation with tiny gains. For delays we deduct the difference in a later month.',
        'The 5% target uses original histories from 2005–2016. Warning counts in the later sample can differ.',
    ]
    for y,line in zip([.17,.145,.12,.095,.07],footer):
        fig.text(.035,y,line,fontsize=11.4,va='top')
    if group=='top_quintile':
        fig.text(.035,.044,'January 2017–December 2025. The cutoffs and the 39 strategies stay the same across edits.',fontsize=11.4,va='top')
    else:
        fig.text(.035,.044,'January 2017–December 2025. Bold numbers show the highest count for each edit. Shading marks the B or D and A or Z rows.',fontsize=11.4,va='top')
    fig.text(.967,.022,str(page),ha='right',fontsize=11)
    return fig,values

def frontier_figure(named,matched,design,page):
    data=named[(named.group=='all')&(named.cap<=20)]
    assert len(data)==7980
    specs={x['id']:x for x in design['policies']}
    rule_order={x['id']:i for i,x in enumerate(design['policies'])}
    anchor=matched[(matched.group=='all')&(matched.cap==3)].copy()
    assert len(anchor)==380
    anchor['families']=anchor.policy.map(lambda p:specs[p]['count'])
    anchor['rule_order']=anchor.policy.map(rule_order)
    fig,axes=plt.subplots(2,5,figsize=PAGE_SIZE,sharex=True,sharey=True)
    fig.subplots_adjust(left=.07,right=.975,top=.80,bottom=.245,wspace=.15,hspace=.75)
    fig.text(.035,.965,'Three named rules for each reporting change',fontsize=22,fontweight='bold',va='top')
    fig.text(.035,.923,'For each edit, we pick the three rules that catch the most edited histories with up to three warnings on unchanged histories.',fontsize=13,va='top')
    fig.text(.035,.895,'194 US strategies, 2017–2025. Each plot follows the same three rules as we relax the warning limit. Lines overlap when counts match.',fontsize=12.5,va='top')
    styles=[('black','-',2.15),('.45','--',1.9),('black',':',2.05)]
    selections=[]
    for ax,mechanism,title in zip(axes.ravel(),MECHANISMS,TITLES):
        ranked=anchor[anchor.mechanism==mechanism].sort_values(['altered','baseline','families','rule_order'],ascending=[False,True,True,True])
        assert len(ranked)==38 and ranked.policy.nunique()==38
        chosen=ranked.head(3)
        assert chosen.policy.nunique()==3
        selections.append({'mechanism':mechanism,'rules':chosen[['policy','baseline','altered','families','rule_order']].to_dict('records')})
        for (_,row),(color,linestyle,width) in zip(chosen.iterrows(),styles):
            r=data[(data.mechanism==mechanism)&(data.policy==row.policy)].sort_values('cap')
            assert r.cap.tolist()==list(range(21)) and r.altered.is_monotonic_increasing
            at_three=r[r.cap==3].iloc[0]
            assert int(at_three.baseline)==int(row.baseline) and int(at_three.altered)==int(row.altered)
            label=short_rule(row.policy)
            ax.step(r.cap,r.altered,where='post',label=label,color=color,linestyle=linestyle,linewidth=width)
        ax.axvline(3,color='.7',linewidth=.8,linestyle='-.',zorder=0)
        ax.set_title(title,fontsize=14,pad=15)
        ax.set_xlim(0,20);ax.set_ylim(0,198)
        ax.set_xticks([0,3,5,10,15,20]);ax.set_yticks([0,50,100,150,194])
        ax.tick_params(labelsize=11.5)
        ax.grid(axis='y',color='.9',linewidth=.65)
        ax.set_axisbelow(True)
        ax.legend(loc='upper left',bbox_to_anchor=(0,-.125),frameon=False,fontsize=10.7,handlelength=2.7,borderaxespad=0,labelspacing=.35)
    fig.text(.025,.545,'Altered histories flagged',rotation=90,ha='center',va='center',fontsize=14)
    fig.text(.52,.122,'Maximum unchanged histories flagged',ha='center',fontsize=14)
    fig.text(.035,.087,'B compares small gains and losses. D checks for too few losing months. A checks whether consecutive months move together. Z looks for tiny gains near zero.',fontsize=11.5,va='top')
    fig.text(.035,.06,"Each rule gets one cutoff. Or means any check can trigger a warning. The vertical line marks three warnings on unchanged histories.",fontsize=11.2,va='top')
    fig.text(.035,.035,'If two rules flag the same number of edited histories, we prefer fewer warnings on unchanged histories, then fewer checks, then their order in the tables.',fontsize=11.4,va='top')
    fig.text(.967,.022,str(page),ha='right',fontsize=11)
    return fig,selections

def main():
    setup_fonts();FIGURES.mkdir(exist_ok=True)
    comparison=load('all_reporting_comparison.csv')
    frontier=load('all_reporting_frontiers.csv')
    matched=load('all_reporting_matched_counts.csv')
    named=load('all_reporting_named_frontiers.csv')
    joint=load('all_reporting_joint_curves.csv')
    summary=json.loads((ROOT/'data/all_reporting_comparison.json').read_text(encoding='utf-8'))
    design=json.loads((ROOT/'data/frozen_design.json').read_text(encoding='utf-8'))
    assert len(comparison)==3420 and len(frontier)==3910 and len(matched)==9120 and len(joint)==11514 and len(named)==23940
    assert comparison.policy.nunique()==38 and comparison.mechanism.nunique()==10
    assert set(comparison.mechanism)==set(MECHANISMS)
    # The supplied deltas must reconcile to their named comparators before rendering.
    for label,policy in [('original_pair','OR:B+D'),('new_pair','OR:A+Z')]:
        keys=['group','mechanism','budget']
        reference=comparison[comparison.policy==policy][keys+['baseline','altered']]
        merged=comparison.merge(reference,on=keys,suffixes=('','_ref'),validate='many_to_one')
        for field in ['baseline','altered']:
            np.testing.assert_array_equal(merged[f'{field}_minus_{label}'],merged[field]-merged[f'{field}_ref'])
    pdf=FIGURES/'reporting_matrix_appendix.pdf'
    metadata={'Title':'Return screening across ten reporting changes','Subject':'Complete warning-count matrices and matched-allowance curves','Creator':'Matplotlib','Author':''}
    figures=[]
    with PdfPages(pdf,metadata=metadata) as pages:
        specs=[
            ('altered','baseline','Warnings across ten reporting changes','All 38 rules use the older 5% warning target. The main sample has 194 US stock strategies.',False),
            ('altered_minus_original_pair','baseline_minus_original_pair','How the warning counts compare with B or D','All rules use the older 5% warning target. The number of unchanged histories flagged later can differ between rules.',True),
            ('altered_minus_new_pair','baseline_minus_new_pair','How the warning counts compare with A or Z','All rules use the older 5% warning target. The number of unchanged histories flagged later can differ between rules.',True),
        ]
        rendered=[]
        for page,(field,baseline,title,subtitle,diff) in enumerate(specs,1):
            fig,values=matrix_figure(comparison,design,field,baseline,title,subtitle,page,difference=diff)
            assert np.isfinite(values).all()
            pages.savefig(fig);plt.close(fig)
            rendered.append({'page':page,'rows':38,'altered_columns':10,'baseline_column':True,'field':field})
        fig,selections=frontier_figure(named,matched,design,4);pages.savefig(fig);plt.close(fig)
        rendered.append({'page':4,'panels':10,'curve_points':630})
    assert len(PdfReader(pdf).pages)==4
    # One optional page preserves the same pooled cutoffs in the strongest quintile.
    top_pdf=FIGURES/'reporting_matrix_top_quintile.pdf'
    with PdfPages(top_pdf,metadata=metadata) as pages:
        fig,_=matrix_figure(comparison,design,'altered','baseline','Warnings across ten changes in the strongest 39 strategies','All 38 rules use the 5% cutoffs set for the full group. The 39 strategies are ranked by their Sharpe ratios before any edits.',1,group='top_quintile')
        pages.savefig(fig);plt.close(fig)
    poppler=Path('C:/Program Files/WindowsApps/OpenAI.CodexPrimaryRuntime.v26-1118-904-0_26.1118.904.0_x64__3k8sg7r9htsxt/dependencies/native/poppler/Library/bin/pdftoppm.exe')
    names=['counts','delta_original','delta_local_serial','frontiers']
    for page,name in enumerate(names,1):
        stem=FIGURES/f'reporting_matrix_{name}'
        subprocess.run([str(poppler),'-f',str(page),'-l',str(page),'-r','135','-singlefile','-png',str(pdf),str(stem)],check=True,capture_output=True)
        figures.append(stem.with_suffix('.png'))
    stem=FIGURES/'reporting_matrix_top_quintile'
    subprocess.run([str(poppler),'-f','1','-l','1','-r','135','-singlefile','-png',str(top_pdf),str(stem)],check=True,capture_output=True)
    figures.append(stem.with_suffix('.png'))
    print(json.dumps({'main_pdf':str(pdf),'main_pages':4,'optional_pdf':str(top_pdf),'optional_pages':1,'pngs':[str(p) for p in figures],
                      'sha256':{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in [pdf,top_pdf]+figures},'pages':rendered,
                      'facet_selections':selections,'joint_cap3_saved':summary['joint_at_caps']['all']['3']},indent=2))

if __name__=='__main__':
    main()
