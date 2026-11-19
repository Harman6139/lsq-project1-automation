"""Short economic handoff tables, derived from full frozen-study outputs."""
from pathlib import Path
import json

import numpy as np
import pandas as pd

ROOT=Path(__file__).resolve().parents[1]


def load(name):
    return pd.read_csv(ROOT/'tables'/f'{name}.csv',float_precision='round_trip')


def main():
    original=load('point_rates_original')
    primary=original[(original.months==108)&(original.representation=='spread')&
                     (original.end=='2025-12')&(original.group=='all')&(original.budget==.05)]
    external=load('external_rates')
    world=external[(external.source=='JKP_world')&(external.group=='all')&(external.budget==.05)]
    comparison=[]
    for source,frame in [('US factor portfolios',primary),('World factor portfolios',world)]:
        for mechanism,label in [('unmodified','Unchanged records'),('relative_delay3','Small losses recognised 3 months later'),('smooth50','Returns averaged across adjacent months')]:
            pair=[]
            for policy in ['OR:B+D','OR:A+Z']:
                row=frame[(frame.mechanism==mechanism)&(frame.policy==policy)].iloc[0]
                pair.append(row)
            comparison.append(dict(source=source,case=label,mechanism=mechanism,n=int(pair[0]['n']),
                old_pair_warnings=int(pair[0].altered),local_serial_pair_warnings=int(pair[1].altered),
                old_pair_baseline=int(pair[0].baseline),local_serial_pair_baseline=int(pair[1].baseline),
                old_pair_new=int(pair[0].new),local_serial_pair_new=int(pair[1].new),reference_budget=.05))
    pd.DataFrame(comparison).to_csv(ROOT/'tables/handoff_comparison.csv',index=False)

    old=ROOT.parent/'assignment_9'
    stats=pd.read_csv(old/'tables/descriptive_statistics.csv')
    stats=stats[(stats.weighting=='original')&(stats.representation=='spread')]
    reports=pd.read_csv(old/'tables/reporting_point.csv',float_precision='round_trip')
    reports=reports[(reports.weighting=='original')&(reports.representation=='spread')&
                    (reports.months==108)&(reports.delta==.01)&(reports.probability==1)&(reports.lag.astype(str)=='3')]
    initial=[]
    for method,label in [('conventional_any','Original conventional rules'),('ordinary_calibrated','Ordinary historical cutoff'),('selection_calibrated','Higher selection cutoff')]:
        row=reports[reports.method==method].iloc[0]
        initial.append(dict(approach=label,n=194,unchanged_warnings=int(row.baseline_alerts),altered_warnings=int(row.altered_alerts),new_warnings=int(row.new_alerts)))
    pd.DataFrame(initial).to_csv(ROOT/'tables/naive_results.csv',index=False)

    choices=load('policy_choices_original')
    choices=choices[(choices.months==108)&(choices.representation=='spread')&(choices.left_out=='none')&(choices.budget==.05)]
    quantity=[]
    for choice in choices.itertuples():
        for mechanism in ['unmodified','relative_delay3','relative_half_delay3','smooth25','smooth50','smooth75','fixed_delay3']:
            row=primary[(primary.policy==choice.policy)&(primary.mechanism==mechanism)].iloc[0]
            quantity.append(dict(scope=str(choice.scope),policy=choice.policy,families=choice.families,
                training_new_warning_rate=choice.training_new_warning_rate,mechanism=mechanism,n=int(row['n']),
                baseline=int(row.baseline),altered=int(row.altered),new=int(row.new),budget=.05))
    pd.DataFrame(quantity).to_csv(ROOT/'tables/quantity_comparison.csv',index=False)
    folds=load('strategy_fold_rates');folds=folds[folds.budget==.05]
    fold_summary=folds.groupby(['scope','mechanism'])[['n','baseline','altered','new','changed']].sum().reset_index()
    fold_summary.to_csv(ROOT/'tables/strategy_fold_summary.csv',index=False)

    cpz=pd.read_csv(ROOT/'data/external/cpz_published_monthly_1967_2016.csv',float_precision='round_trip')
    cpz.index=pd.PeriodIndex(cpz.month,freq='M')
    samples=[('first108','1992-01','2000-12'),('second108','2001-01','2009-12'),('final108_overlap','2008-01','2016-12'),('published_test300','1992-01','2016-12')]
    high=[]
    for sample,start,end in samples:
        x=cpz.SDF.loc[start:end].to_numpy();sd=x.std(ddof=1)
        row=dict(sample=sample,start=start,end=end,n=len(x),mean=float(x.mean()),sd=float(sd),excess_sharpe=float(x.mean()/sd),
            losing_months=int((x<0).sum()),small_losses_eligible=int(((x>=-.25*sd)&(x<0)).sum()))
        for policy,label in [('OR:B+D','old_pair'),('OR:A+Z','local_serial_pair'),('OR:B+A+Z','three_rules')]:
            for mechanism,suffix in [('unmodified','original'),('relative_delay3','delay3'),('smooth50','smoothed')]:
                r=external[(external.source=='CPZ_author')&(external['sample']==sample)&(external.group=='SDF')&
                           (external.budget==.05)&(external.policy==policy)&(external.mechanism==mechanism)].iloc[0]
                row[label+'_'+suffix]=int(r.altered)
        high.append(row)
    pd.DataFrame(high).to_csv(ROOT/'tables/exceptional_history_summary.csv',index=False)
    summaries=dict(
        initial_unmodified_count=len(stats),initial_unmodified_alerts=int(stats.conventional_any.sum()),
        initial_cutoff_comparison=initial,frontier_comparison=comparison,
        selected_choices=choices[['scope','policy','families','training_new_warning_rate']].to_dict(orient='records'),
        exceptional_history=high,
        interpretive_takeaways=[
            'The initial experiment showed sparse unchanged warnings and the familiar cost of a higher cutoff.',
            'The frontier exercise compares different types and quantities, not only thresholds.',
            'A local zero-bin score and positive serial dependence cover different imposed reporting changes.',
            'Adding third/fourth checks gave little extra coverage on the later factor panel, but the high-Sharpe first GAN test block needed the bias check for its imposed loss delay.',
            'Same older-reference warning budget; actual later investigation counts are shown separately.',
            'Highest reported GAN Sharpe is an author-backtest segment, not a live fund NAV; later performance weakened.',
            'Existing papers already combine alerts and compare costs; no new frontier method is claimed.'
        ],execution_seconds={p.stem:json.loads(p.read_text()).get('seconds') for p in sorted((ROOT/'data').glob('execution_*.json'))})
    (ROOT/'data/results_summary.json').write_text(json.dumps(summaries,indent=2)+'\n')
    print(json.dumps(dict(status='handoff summaries built',initial_alerts=summaries['initial_unmodified_alerts'],
                         first_high_sharpe=high[0]['excess_sharpe'],execution_seconds=summaries['execution_seconds']),indent=2))


if __name__=='__main__': main()
