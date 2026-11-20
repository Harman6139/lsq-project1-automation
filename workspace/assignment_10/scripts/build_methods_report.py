"""Build the report table and plot from the frozen reporting comparison."""
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import pandas as pd

from compare_all_reporting import LABELS, ORIGINAL, PAIR, ROOT
from frontier_engine import design


def rule_name(rule):
    if rule.startswith('OR:'):
        return ' or '.join(rule.split(':')[1].split('+'))
    if rule.startswith('MAJ:'):
        letters = rule.split(':')[1].split('+')
        return ' and '.join(letters) if len(letters) == 2 else 'Majority of ' + ', '.join(letters)
    if rule.startswith('MEAN:'):
        return 'Average of ' + ', '.join(rule.split(':')[1].split('+'))
    return 'Weighted B, D, A, Z' if rule.startswith('PCA:') else rule


def rank_at_three(data, metric):
    specs = design()['policies']
    family_count = {spec['id']: spec['count'] for spec in specs}
    order = {spec['id']: i for i, spec in enumerate(specs)}
    choices = data[data.baseline.le(3)].copy()
    choices['n_checks'] = choices.policy.map(family_count)
    choices['rule_order'] = choices.policy.map(order)
    choices = choices.sort_values([metric, 'baseline', 'n_checks', 'rule_order', 'budget'],
                                  ascending=[False, True, True, True, True])
    return choices.drop_duplicates('policy').head(3)


def plot_common_cutoff():
    data = pd.read_csv(ROOT / 'tables/all_reporting_joint_curves.csv', float_precision='round_trip')
    data = data[data.group == 'all']
    plt.rcParams.update({
        'font.family': 'Times New Roman', 'font.size': 9,
        'axes.spines.top': False, 'axes.spines.right': False,
    })
    fig, axes = plt.subplots(1, 2, figsize=(7, 1.95), sharey=True)
    caps = range(11)
    rankings = []
    for ax, metric, title in zip(
        axes, ['mean_altered', 'min_altered'],
        ['Average across the ten edits', 'Fewest flagged in any edit']
    ):
        top = rank_at_three(data, metric)
        rankings.append(top.policy.tolist())
        for row, style, shade in zip(top.itertuples(), ['-', '--', ':'], ['black', '.38', '.5']):
            block = data[data.policy == row.policy]
            values = [block.loc[block.baseline <= cap, metric].max() for cap in caps]
            ax.step(caps, values, where='post', label=rule_name(row.policy),
                    linestyle=style, color=shade, lw=1.4)
        ax.axvline(3, color='.76', lw=.8)
        ax.set(title=title, ylim=(0,198), xlim=(0,10), xticks=[0,1,3,5,10])
        ax.grid(axis='y', alpha=.16)
    assert rankings[0] == rankings[1]
    axes[0].set_ylabel('Edited copies flagged')
    fig.supxlabel('Cap on warnings on unchanged histories', y=.163, fontsize=9)
    fig.legend(*axes[0].get_legend_handles_labels(), ncol=3, frameon=False,
               loc='lower center', bbox_to_anchor=(.54,-.01))
    fig.subplots_adjust(left=.072, right=.99, top=.82, bottom=.33, wspace=.085)
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
