"""Print and display the three leading screens for the three-month loss edit."""
from pathlib import Path
from hashlib import sha256
import json

import matplotlib
matplotlib.use('Agg')
from matplotlib import pyplot as plt
import pandas as pd

from build_methods_report import rank_at_three, rule_name
from frontier_engine import ROOT

STEM = 'Return_Screening_Frontier_Explained'


def main():
    source = ROOT / 'tables/all_reporting_named_frontiers.csv'
    all_points = pd.read_csv(source, float_precision='round_trip')
    points = all_points[(all_points.group == 'all') & (all_points.mechanism == 'relative_delay3')]
    best = rank_at_three(points[points.cap == 3], 'altered')
    assert best.policy.tolist() == ['OR:D+Z', 'OR:B+D+Z', 'OR:D+A+Z']
    plt.rcParams.update({'font.family':'Times New Roman','font.size':13,
                         'axes.spines.top':False,'axes.spines.right':False,
                         'svg.fonttype':'none','pdf.fonttype':42})
    fig, ax = plt.subplots(figsize=(10,6))
    fig.subplots_adjust(left=.11,right=.97,bottom=.29,top=.78)
    fig.text(.085,.92,'Which checks find losses recorded three months late?',weight='bold',fontsize=21)
    fig.text(.085,.856,'Three arrangements tied at 192 of 194 edited histories, with one warning on an unchanged history.',fontsize=12.5)
    for row, style, color in zip(best.itertuples(), ['-','--',':'], ['black','.32','.51']):
        data = points[points.policy == row.policy].sort_values('cap')
        ax.step(data.cap,data.altered,where='post',label=rule_name(row.policy),ls=style,color=color,lw=2)
    ax.axvline(3,color='.73',lw=1.2)
    ax.set(xlim=(0,20),ylim=(0,202),xticks=[0,3,5,10,15,20],yticks=[0,50,100,150,194],
           xlabel='Maximum warnings allowed on unchanged histories',ylabel='Edited histories flagged')
    ax.grid(axis='y',alpha=.15)
    fig.legend(*ax.get_legend_handles_labels(),ncol=3,loc='lower center',bbox_to_anchor=(.54,.155),frameon=False)
    fig.text(.085,.105,'B = small gains versus small losses. D = unusually few losing months.',fontsize=11)
    fig.text(.085,.073,'A = similar returns in consecutive months. Z = tiny gains piling up just above zero.',fontsize=11)
    fig.text(.085,.035,'The lines follow the same three arrangements as the warning cap changes. Lines can overlap.',fontsize=11)
    files = []
    for ext in ['pdf','svg','png']:
        path = ROOT/'figures'/f'{STEM}.{ext}'
        fig.savefig(path,dpi=180,facecolor='white')
        files.append(dict(file='figures/'+path.name,sha256=sha256(path.read_bytes()).hexdigest()))
    plt.close(fig)
    metadata = dict(source=str(source.relative_to(ROOT)), source_sha256=sha256(source.read_bytes()).hexdigest(),
        rules=best[['policy','baseline','altered','budget']].to_dict('records'), selection_cap=3,
        cap_range=[0,20], files=files)
    (ROOT/'data/plain_english_frontier_metadata.json').write_text(json.dumps(metadata,indent=2)+'\n',encoding='utf-8')


if __name__ == '__main__':
    main()
