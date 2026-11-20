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
    'Losses up to 1%\n3-month delay', 'Averaging: 25%\nprevious month',
    'Averaging: 50%\nprevious month', 'Averaging: 75%\nprevious month',
]
TITLES = [
    'Small losses left out', 'Small losses delayed\n1 month',
    'Small losses delayed\n3 months', 'Small losses delayed\n6 months',
    'Half the small losses\ndelayed 3 months', 'Losses up to 1% left out',
    'Losses up to 1%\ndelayed 3 months', 'Averaging: 25%\nprevious month',
    'Averaging: 50%\nprevious month', 'Averaging: 75%\nprevious month',
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

def short_rule(policy, primary):
    if ':' not in policy:
        label = policy
    else:
        kind, fields = policy.split(':')
        label = {'OR':'OR', 'MAJ':'Majority', 'MEAN':'Mean', 'PCA':'PC'}[kind]+' '+fields
    return label+(' *' if not primary else '')

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
        detail='Positive numbers mean more warnings than the named pair; negative numbers mean fewer. The unchanged column shows the difference in background warnings.'
    else:
        detail=f'Each altered-data cell counts all histories flagged, including any flagged before the change. The unchanged column shows the background warning count out of {n}.'
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
    ax.set_yticks(range(38),[short_rule(s['id'],s['primary']) for s in specs])
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
        'Checks: B = bias ratio; D = fitted-normal loss-count deficit; A = positive serial dependence; Z = local contrast around zero.',
        'Rules: OR flags a high score from any input; Majority requires more than half; Mean averages historical ranks; PC uses the first principal component. * Secondary comparator.',
        'Small losses lie between -0.25 baseline monthly SD and zero, replaced by +0.0125 SD. Temporary cases return the full hidden amount after the stated lag.',
        'Averaging combines the current and previous monthly return. Each rule has its own cutoff fitted to 2005-2016 reference data; the common 5% allowance does not equalize later warning counts.',
    ]
    for y,line in zip([.166,.137,.108,.079],footer):
        fig.text(.035,y,line,fontsize=11.8,va='top')
    if group=='top_quintile':
        fig.text(.035,.045,'The 39 strongest original-return Sharpe ratios define this group; membership stays fixed after the reporting change. The same pooled cutoffs are used.',fontsize=11.5,va='top')
    else:
        fig.text(.035,.045,'Source: saved original-weight monthly stock-strategy comparisons, January 2017-December 2025. Bold altered-data cells mark a column maximum; shaded rows are the two comparison pairs.',fontsize=11.5,va='top')
    fig.text(.967,.022,str(page),ha='right',fontsize=11)
    return fig,values

def frontier_figure(frontiers,page):
    data=frontiers[(frontiers.group=='all')&(frontiers.cap<=20)]
    assert len(data)==210
    fig,axes=plt.subplots(2,5,figsize=PAGE_SIZE,sharex=True,sharey=True)
    fig.subplots_adjust(left=.07,right=.975,top=.835,bottom=.22,wspace=.15,hspace=.43)
    fig.text(.035,.965,'Coverage at the same unchanged-warning allowance',fontsize=22,fontweight='bold',va='top')
    fig.text(.035,.923,'All 38 rules versus the original pair B+D and the local/serial pair A+Z; 194 US strategy histories, January 2017-December 2025.',fontsize=13,va='top')
    fig.text(.035,.895,'Horizontal axis: allowance of up to the stated number of unchanged warnings. Vertical axis: total altered histories flagged.',fontsize=12.5,va='top')
    styles=[('all_rules_max','Best of all 38','black','-',2.15),('original_pair','Original pair: B+D','.45','--',1.8),('new_pair','Local + serial: A+Z','black',':',2.0)]
    for ax,mechanism,title in zip(axes.ravel(),MECHANISMS,TITLES):
        r=data[data.mechanism==mechanism].sort_values('cap')
        assert r.cap.tolist()==list(range(21))
        assert (r.all_rules_max>=r.original_pair).all() and (r.all_rules_max>=r.new_pair).all()
        for field,label,color,linestyle,width in styles:
            assert r[field].is_monotonic_increasing
            ax.step(r.cap,r[field],where='post',label=label,color=color,linestyle=linestyle,linewidth=width)
        ax.set_title(title,fontsize=14,pad=15)
        ax.set_xlim(0,20);ax.set_ylim(0,198)
        ax.set_xticks([0,5,10,15,20]);ax.set_yticks([0,50,100,150,194])
        ax.tick_params(labelsize=11.5)
        ax.grid(axis='y',color='.9',linewidth=.65)
        ax.set_axisbelow(True)
    fig.text(.025,.545,'Altered histories flagged',rotation=90,ha='center',va='center',fontsize=14)
    fig.text(.52,.16,'Maximum unchanged histories flagged',ha='center',fontsize=14)
    handles,labels=axes[0,0].get_legend_handles_labels()
    fig.legend(handles,labels,loc='lower center',bbox_to_anchor=(.52,.105),ncol=3,frameon=False,fontsize=13,handlelength=3.4,columnspacing=3)
    fig.text(.035,.072,'Each curve takes the best saved older-data cutoff within its warning allowance. The all-38 envelope also chooses the rule separately for each reporting change and allowance.',fontsize=11.8,va='top')
    fig.text(.035,.043,'This is a descriptive envelope for the saved 101-cutoff grid. It is not one rule selected before evaluation, and an unchanged-warning allowance is not total workload when altered histories are prevalent.',fontsize=11.8,va='top')
    fig.text(.967,.022,str(page),ha='right',fontsize=11)
    return fig

def main():
    setup_fonts();FIGURES.mkdir(exist_ok=True)
    comparison=load('all_reporting_comparison.csv')
    frontier=load('all_reporting_frontiers.csv')
    matched=load('all_reporting_matched_counts.csv')
    joint=load('all_reporting_joint_curves.csv')
    summary=json.loads((ROOT/'data/all_reporting_comparison.json').read_text(encoding='utf-8'))
    design=json.loads((ROOT/'data/frozen_design.json').read_text(encoding='utf-8'))
    assert len(comparison)==3420 and len(frontier)==3910 and len(matched)==9120 and len(joint)==11514
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
            ('altered','baseline','Warnings across ten reporting changes','All 38 rules at the same older 5% reference allowance; 194 US strategy histories. Counts are shown in every cell.',False),
            ('altered_minus_original_pair','baseline_minus_original_pair','Difference from the original pair B+D','Same older 5% reference allowance. These are count differences; the actual unchanged warning burden can differ between rules.',True),
            ('altered_minus_new_pair','baseline_minus_new_pair','Difference from the local/serial pair A+Z','Same older 5% reference allowance. These are count differences; the actual unchanged warning burden can differ between rules.',True),
        ]
        rendered=[]
        for page,(field,baseline,title,subtitle,diff) in enumerate(specs,1):
            fig,values=matrix_figure(comparison,design,field,baseline,title,subtitle,page,difference=diff)
            assert np.isfinite(values).all()
            pages.savefig(fig);plt.close(fig)
            rendered.append({'page':page,'rows':38,'altered_columns':10,'baseline_column':True,'field':field})
        fig=frontier_figure(frontier,4);pages.savefig(fig);plt.close(fig)
        rendered.append({'page':4,'panels':10,'curve_points':630})
    assert len(PdfReader(pdf).pages)==4
    # One optional page preserves the same pooled cutoffs in the strongest quintile.
    top_pdf=FIGURES/'reporting_matrix_top_quintile.pdf'
    with PdfPages(top_pdf,metadata=metadata) as pages:
        fig,_=matrix_figure(comparison,design,'altered','baseline','The strongest-return quintile: warnings across ten changes','All 38 rules, the same pooled older 5% reference cutoffs, and the fixed 39 strongest original-return Sharpe ratios.',1,group='top_quintile')
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
                      'joint_cap3_saved':summary['joint_at_caps']['all']['3']},indent=2))

if __name__=='__main__':
    main()
