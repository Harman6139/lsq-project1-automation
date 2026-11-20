"""Build the report table and plot from the frozen reporting comparison."""
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from compare_all_reporting import LABELS, ORIGINAL, PAIR, ROOT


def plot_common_cutoff():
    data = pd.read_csv(ROOT / 'tables/all_reporting_joint_curves.csv')
    data = data[data.group == 'all']
    plt.rcParams.update({
        'font.family': 'Times New Roman', 'font.size': 9,
        'axes.spines.top': False, 'axes.spines.right': False,
    })
    fig, axes = plt.subplots(1, 2, figsize=(7, 1.85), sharey=True)
    labels = ['All 38', 'Paper pair', 'Newer pair', 'Checks 2, 3 and 4']
    caps = range(11)
    for ax, metric, title in zip(
        axes, ['mean_altered', 'min_altered'],
        ['Average across the ten edits', 'Fewest flagged in any edit']
    ):
        for rule, label, style, color in zip(
            [None, ORIGINAL, PAIR, 'OR:D+A+Z'], labels,
            ['-', ':', '--', '-.'], ['black', '0.48', '0.30', '0.55']
        ):
            block = data if rule is None else data[data.policy == rule]
            values = [block.loc[block.baseline <= cap, metric].max() for cap in caps]
            ax.step(caps, values, where='post', label=label, linestyle=style, color=color)
        ax.set(title=title, ylim=(0,198), xlim=(0,10), xticks=[0,1,3,5,10])
        ax.grid(axis='y', alpha=.16)
    axes[0].set_ylabel('Edited copies flagged')
    fig.supxlabel('Cap on warnings on original histories', y=.152, fontsize=9)
    fig.legend(*axes[0].get_legend_handles_labels(), ncol=4, frameon=False,
               loc='lower center', bbox_to_anchor=(.54,-.015))
    fig.subplots_adjust(left=.072, right=.99, top=.82, bottom=.32, wspace=.085)
    fig.savefig(ROOT/'figures/reporting_joint_tradeoff.png', dpi=230)
    plt.close(fig)


def main():
    points = pd.read_csv(ROOT/'tables/all_reporting_comparison.csv', float_precision='round_trip')
    points = points[(points.group == 'all') & (points.budget == .05)]
    fixed = points.pivot(index='mechanism', columns='policy', values='altered')
    frontiers = pd.read_csv(ROOT/'tables/all_reporting_frontiers.csv')
    capped = frontiers[(frontiers.group == 'all') & (frontiers.cap == 3)].set_index('mechanism')
    labels = [
        'Leave out small losses', 'Delay one month', 'Delay three months',
        'Delay six months', 'Delay half the losses', 'Leave out losses up to 1\\%',
        'Delay losses up to 1\\%', 'Average, 25\\% previous month',
        'Average, 50\\% previous month', 'Average, 75\\% previous month'
    ]
    rows = []
    for m, label in zip(LABELS, labels):
        scores = [
            fixed.loc[m, ORIGINAL], fixed.loc[m, PAIR], fixed.loc[m].max(),
            *capped.loc[m, ['original_pair','new_pair','all_rules_max']]
        ]
        rows.append(label+' & '+' & '.join(str(int(v)) for v in scores)+r'\\')
    template = Path(__file__).with_name('methods_note_body.tex').read_text(encoding='utf-8-sig')
    (ROOT/'Return_Screening_Frontier.tex').write_text(
        template.replace('@@TABLE@@', '\n'.join(rows)), encoding='utf-8'
    )
    plot_common_cutoff()


if __name__ == '__main__':
    main()
