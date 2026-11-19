"""Produce a short economic handoff and the matching email draft."""
from pathlib import Path
import json
import re
import pandas as pd

ROOT=Path(__file__).resolve().parents[1]
STEM='Assignment_10_Return_Screening_Frontier_Handoff'


def main():
    summary=json.loads((ROOT/'data/results_summary.json').read_text())
    comparison=pd.read_csv(ROOT/'tables/handoff_comparison.csv')
    lines=[]
    for i,row in comparison.iterrows():
        market='US' if row.source.startswith('US') else 'World'
        label={'unmodified':'Unchanged','relative_delay3':'Losses delayed 3 months','smooth50':'Smoothed returns'}[row.mechanism]
        if i in [0,3]:
            lines.append(r'\multicolumn{3}{l}{\textit{'+f'{market}: {row.n} histories'+r'}} \\')
        label={'unmodified':'Unchanged','relative_delay3':'Delay: 3 months','smooth50':'Smoothed'}[row.mechanism]
        lines.append(f'{label} & {row.old_pair_warnings} & {row.local_serial_pair_warnings} '+r'\\')
        if i==2: lines.append(r'\midrule')
    table='\n'.join(lines)
    text=r'''\documentclass[12pt,letterpaper]{article}
\usepackage[margin=0.9in]{geometry}
\usepackage{fontspec}\setmainfont{Times New Roman}
\usepackage{booktabs,array,amsmath}
\usepackage[hidelinks]{hyperref}
\setlength{\parindent}{0pt}\setlength{\parskip}{8pt}
\setlength{\tabcolsep}{8pt}\renewcommand{\arraystretch}{1.17}
\pagestyle{empty}
\newcommand{\lead}[1]{\textbf{#1}}
\begin{document}
\begin{center}
{\Large\bfseries Return-screening frontier: handoff}\\[5pt]
{19 November 2026}
\end{center}

\lead{Objective.} Which checks, and how many, catch more reporting changes for the same investigation burden?

\lead{Initial exercise.} One of 195 unchanged histories was flagged. Raising the cutoff reduced delayed-loss warnings from 111 to 66 of 194: the familiar tradeoff.

\lead{Frontier test.} We compared 38 arrangements of four checks: small-win/loss balance, loss counts, local bunching near zero, and return persistence; calibrated earlier, tested later.

\begin{center}
\begin{tabular}{lrr}
\toprule
Records & Original pair & Local + serial \\
\midrule
@@TABLE@@
\bottomrule
\end{tabular}
\end{center}
{\small Same 5\% older-reference allowance; warnings shown. Original pair: first two checks. Local/serial: last two.}

\lead{Takeaway.} Complementary checks helped. In a backtest (monthly excess Sharpe 1.53), adding bias caught a delay the local/serial pair missed. \href{https://doi.org/10.1093/rfs/hhs085}{Frontier methods are established}; the useful increment is where combinations transfer or fail.
\end{document}
'''.replace('@@TABLE@@',table)
    (ROOT/f'{STEM}.tex').write_text(text,encoding='utf-8')
    email_path=ROOT/'Email_to_Professor_Boyle_Frontier_Handoff.txt'
    email=email_path.read_text(encoding='utf-8') if email_path.exists() else ''
    (ROOT/'data/handoff_metadata.json').write_text(json.dumps(dict(
        report_title='Return-screening frontier: handoff',
        email_words=len(email.split()),numeric_basis='data/results_summary.json; tables/handoff_comparison.csv',
        initial_counts=summary['initial_cutoff_comparison'],table_rows=len(comparison)),indent=2)+'\n')
    print(json.dumps(dict(tex=str(ROOT/f'{STEM}.tex'),email_words=len(email.split()),table_rows=len(comparison)),indent=2))


if __name__=='__main__': main()
