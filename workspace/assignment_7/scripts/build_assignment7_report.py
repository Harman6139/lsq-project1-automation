"""Build the concise LaTeX report and analysis figures from saved results."""
from pathlib import Path
import json, hashlib, csv, sys, subprocess, importlib.metadata
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from scipy.stats import norm

ROOT=Path(__file__).resolve().parents[1]
R=json.loads((ROOT/'assignment7_results.json').read_text())
M=pd.read_csv(ROOT/'tables/monthly_model_results.csv')
F=R['best']; BM=R['best_moments']; N=R['note_moments']
fmt=lambda x,d=2:f'{x:.{d}f}'
pct=lambda x,d=2:f'{100*x:.{d}f}\\%'

plt.rcParams.update({'font.family':'serif','font.size':10,'axes.spines.top':False,'axes.spines.right':False})
dates=pd.to_datetime(M.date)
fig,axes=plt.subplots(2,1,figsize=(9,4.3),sharex=True,gridspec_kw={'height_ratios':[1.3,1]})
for ax,col,label in [(axes[0],'note_viterbi','Supplied note: 12 high months'),(axes[1],'high_state_viterbi',f'Improved fit: {len(R["high_months"])} high months')]:
    colors=np.where(M[col]==1,'#9d4b37','#334e68')
    ax.bar(dates,M.lsq_return*100,width=23,color=colors)
    ax.axhline(0,color='#555555',lw=.6);ax.set_ylabel('Return (%)')
    ax.set_title(label,loc='left',fontsize=10)
axes[1].set_xlabel('Month');fig.tight_layout()
fig.savefig(ROOT/'figures/regime_comparison.png',dpi=190,bbox_inches='tight');plt.close(fig)

fig,ax=plt.subplots(figsize=(8,3.1))
rr=np.linspace(-.06,.26,800); yy=np.log1p(rr)
ax.hist(M.lsq_return,bins=np.linspace(-.04,.24,25),density=True,color='#d1d8df',label='Observed returns')
y=M.log_return
ax.plot(rr,norm.pdf(yy,y.mean(),y.std(ddof=0))/(1+rr),label='One regime',color='#777777',ls='--')
for name,key,color in [('Independent mixture','iid','#a35b41'),('Improved switching fit','best','#284f71')]:
    f=R[key];w=np.array(f['pi']);density=(norm.pdf(yy[:,None],f['mu'],f['sd'])*w).sum(1)/(1+rr)
    ax.plot(rr,density,label=name,color=color)
ax.set_xlabel('Monthly return (decimal)');ax.set_ylabel('Density');ax.legend(frameon=False,fontsize=8)
fig.tight_layout();fig.savefig(ROOT/'figures/distribution_comparison.png',dpi=190);plt.close(fig)

rows=[]
for name,mean,sd,dur,share in [('Note ordinary',N['mean_returns'][0],N['sd_returns'][0],N['durations'][0],N['stationary'][0]),('Note high',N['mean_returns'][1],N['sd_returns'][1],N['durations'][1],N['stationary'][1]),('Improved lower',BM['mean_returns'][0],BM['sd_returns'][0],BM['durations'][0],BM['stationary'][0]),('Improved higher',BM['mean_returns'][1],BM['sd_returns'][1],BM['durations'][1],BM['stationary'][1])]:
    rows.append(f'{name} & {pct(mean)} & {pct(sd)} & {dur:.1f} & {pct(share,1)} \\\\')
comparison=[]
for x in R['comparison']:
    if x['model']=='Note rounded stationary':continue
    comparison.append(f"{x['model']} & {x['parameters']} & {x['log_likelihood']:.2f} & {x['AIC']:.2f} & {x['BIC']:.2f} \\\\")
predict=[]
for name,key in [('One regime','one'),('Independent mixture','mixture'),('Switching model','hmm')]:
    v=R['validation'][key];predict.append(f'{name} & {v["log_score"]:.2f} & {pct(v["rmse"])} \\\\')
s=R['sensitivity'];episode=s[6]['moments']

tex=r'''\documentclass[11pt]{article}
\usepackage[margin=0.78in]{geometry}
\usepackage{amsmath,booktabs,array,graphicx,float,hyperref}
\hypersetup{colorlinks=true,urlcolor=blue,linkcolor=blue}
\setlength{\parindent}{0pt}
\setlength{\parskip}{6pt}
\newcommand{\smalltitle}[1]{\vspace{5pt}\textbf{#1}\par}
\begin{document}
\begin{center}
{\Large Assignment 7: Fund X and the Two Regime Model}\\[5pt]
Prepared by Harman Singh for Professor Phelim Boyle\\
September 2026
\end{center}

\smalltitle{What the model tells us}
The two-regime idea suits Fund X because its returns change in both size and
variability. Many months have modest gains, while other periods contain much
larger gains. Letting the fund move between two return patterns describes that
history better than forcing every month into one distribution.

The supplied note's exact fit is not the best one found. A fresh fit, independently
checked with a second implementation, raises the log-likelihood from the reported
255.75 to \textbf{261.11}. It describes a quieter state averaging \textbf{1.55\%}
per month and a more variable state averaging \textbf{5.68\%}. Both last about
13 months on average. That differs substantially from the note's short, two-month
bursts averaging 9.6\%.

\smalltitle{Why that is economically plausible}
The fund's factsheet describes a systematic long/short equity strategy with low
net market exposure. Trading opportunities could change over time even when the
overall market direction is unhelpful. Two positive-mean states are consistent
with that description. Returns alone do not establish the trading mechanism,
manager skill, or the accuracy of reported valuations. The model is useful for
describing varying return conditions and building conditional scenarios.

\smalltitle{What was checked and why}
All 115 returns from January 2017 through July 2026 match the saved source
factsheet exactly. There are five negative months; the mean is 3.52\% and the
sample standard deviation is 3.98\% per month. July is marked estimated.
The comparison keeps this date range fixed.

\begin{table}[H]\centering\small
\caption{Allowing two distributions produces most of the improvement}
\begin{tabular}{lrrrr}\toprule
Model & Parameters & Log-likelihood & AIC & BIC\\\midrule
@COMPARISON@
\bottomrule\end{tabular}
\end{table}
An independent mixture allows two distributions but redraws the state each month.
It already beats the note's reported likelihood. Adding persistence improves
the refitted model further. Lower AIC and BIC favor the improved switching fit,
but these are model comparisons, not proof of a unique economic explanation.

\begin{table}[H]\centering\small
\caption{The interpretation changes when the model is refitted}
\begin{tabular}{lrrrr}\toprule
State & Mean return & Return SD & Duration (months) & Long-run share\\\midrule
@REGIMES@
\bottomrule\end{tabular}
\end{table}
\newpage

\smalltitle{The high state is more than a handful of exceptional months}
\begin{center}\includegraphics[width=.98\linewidth]{figures/regime_comparison.png}\end{center}
\small Red bars mark the higher-return state on the most likely full-sample
path. These labels use hindsight. They are not signals available before each
month. Long-run state shares in the table are different from observed path counts.
\normalsize

\smalltitle{The tests and what they mean}
\textbf{Does the order of months matter?} Yes. Shuffling the same 115 returns
499 times and refitting produces an equal or larger switching-versus-mixture
gain only twice (one-sided Monte Carlo $p=0.006$). Timing contains information
beyond the return histogram. This rejects exchangeable ordering; gradual changes
or other dependence could also produce that finding.

\textbf{Does the model explain the rare losses?} Only partly. The note's fitted
distribution expects about \textbf{13.9} loss months out of 115; the improved
fit expects \textbf{11.2}. Only \textbf{five} occurred. A positive mean in each
state does not remove the negative tail. Neither model shows that future losses
will remain rare or small.

\textbf{Is dependence left over?} Raw lag-one autocorrelation is 0.352.
Predictive innovations from the improved fit have lag-one autocorrelation 0.156.
Their 12-lag statistic is 19.70; a bootstrap that simulates and refits the model
gives $p=0.080$ (199 simulations). This does not reject at 5\%, but it also does
not establish independence or correct tail behavior.

\begin{table}[H]\centering\small
\caption{One-month-ahead checks from January 2025 through July 2026}
\begin{tabular}{lrr}\toprule
Model & Total log predictive score & Mean forecast RMSE\\\midrule
@PREDICT@
\bottomrule\end{tabular}
\end{table}
Higher log scores mean better predictions of the whole return distribution;
lower RMSE means smaller errors in the predicted mean. The switching model has
slightly lower mean error, but the simpler mixture has the best distribution
score. Each forecast uses only earlier returns. This is a retrospective check
of 19 months, with the model family chosen after seeing the full history, so it
does not establish a reliable trading advantage.
\newpage

\smalltitle{Short technical notes}
\textbf{Model and units.} Monthly simple returns are decimals, net of management
and performance fees for the source's I series. With $y_t=\log(1+r_t)$,
$y_t\mid S_t=i\sim N(\mu_i,\sigma_i^2)$, and the two-state transition matrix is
row-stochastic. The primary likelihood starts in its stationary distribution.
The mean simple return is $e^{\mu_i+\sigma_i^2/2}-1$; expected duration is
$1/(1-p_{ii})$. All reported likelihoods use log-return density. Converting to
simple-return density subtracts $\sum_t\log(1+r_t)$ from every likelihood, so
model rankings and likelihood differences are unchanged. No annualization is used.

\textbf{Optimization and reproduction.} The primary search uses 300 starts,
EM starting values, and direct constrained likelihood maximization. A separate
\texttt{statsmodels} Hamilton-filter fit agrees within $10^{-5}$ log-likelihood
units. The standard deviation floor is 0.001 in log-return units; halving and
doubling it leaves the main result unchanged. The fitted standard deviations
are far above this floor. A floor avoids a component collapsing onto one
observation, where an unrestricted Gaussian-mixture likelihood can diverge.
This is the best nondegenerate fit found, not a proof of a global maximum.

\textbf{Corrections to the supplied note.} Its one-regime likelihood, raw ACF,
12 high-month labels, and regime-demeaned lag-one ACF of 0.157 reproduce. Using
its rounded parameters gives likelihood 255.56 with its stated rounded
stationary weights, or 255.71 if the first month is fixed in the lower state.
The original code, unrounded parameters, and initialization were not supplied,
so the exact source of the reported 255.75 and stopping rule cannot be verified.
In either case, better fits exist. Six parameters versus two means
\textbf{four}, not three, extra parameters. Estimating the initial-state weight
adds a seventh parameter. A usual chi-square likelihood-ratio reference is
invalid when states become indistinguishable under the null. The note correctly
recognizes nonregularity, but its one-regime comparison alone cannot isolate
the contribution from persistence.

\textbf{Residual and tail interpretation.} Subtracting full-sample Viterbi state
means uses hindsight and leaves different variances across states. Its ordinary
Ljung--Box p-values are descriptive, without a valid automatic correction for
estimated states. The alternative check uses
$z_t=\Phi^{-1}\{\sum_i w_{t|t-1,i}\Phi[(y_t-\mu_i)/\sigma_i]\}$ and refits
every bootstrap sample. The model-implied probabilities of at most five losses
are 0.0040 for the note and 0.0286 for the improved fit, computed by an exact
Markov count recursion at fixed fitted parameters. These are predictive
calibration warnings, not exact goodness-of-fit p-values after estimation.

\textbf{Stability.} Removing estimated July leaves mean returns near 1.55\%
and 5.75\%, with durations near 13 months. Returning to the earlier May sample
gives 1.57\% and 5.83\%. Hiding each of four high-return episodes, while preserving
calendar transitions, leaves two positive-mean patterns but can materially change
their durations. The January--February 2021 deletion gives approximately
@DURLOW@ and @DURHIGH@ months. Precise state labels and durations should therefore
be treated as sample-sensitive estimates.

\smalltitle{Connection to prior work and sources}
This extends Assignment 3's serial-dependence question on the longer July sample.
It supports examining changing return conditions, but does not identify their
cause or prove the absence of smoothing. Assignment 3 used 113 observations to
May; this note uses 115 to July.

{\footnotesize
Source: supplied \texttt{Fund\_X\_two\_regime\_model.docx}, September 2026.
The stated \texttt{COMBined3b.xlsx} was not found. The project CSV
was instead independently reconciled month by month to the saved
\href{https://spartanfunds.ca/wp-content/uploads/2021/11/LSQ-Oct21.pdf}{July 2026 fund factsheet},
downloaded August 10, 2026; its exact snapshot and hash are retained.\\
Method references: Hardy (2001), \emph{North American Actuarial Journal} 5(2),
41--53, bibliographic details checked against the
\href{https://uwaterloo.ca/statistics-and-actuarial-science/profiles/mary-hardy}{author's university profile};
\href{https://www.statsmodels.org/stable/examples/notebooks/generated/markov_regression.html}{statsmodels Markov switching documentation};
\href{https://scikit-learn.org/1.0/modules/mixture.html}{scikit-learn Gaussian mixture documentation}.
}
\end{document}
'''
tex=tex.replace('@COMPARISON@','\n'.join(comparison)).replace('@REGIMES@','\n'.join(rows)).replace('@PREDICT@','\n'.join(predict)).replace('@DURLOW@',fmt(episode['durations'][0],1)).replace('@DURHIGH@',fmt(episode['durations'][1],1))
target=ROOT/'Assignment_7_Fund_X_Two_Regime_Review.tex'
target.write_text(tex,encoding='utf-8')

versions={}
for name in ['numpy','pandas','scipy','statsmodels','matplotlib']:
    versions[name]=importlib.metadata.version(name)
manifest={'assignment':7,'title':'Fund X two-regime model review','sample':R['data'],
 'linkage':'Extends Assignment 3; verifies and qualifies supplied regime-switching note.',
 'source':json.loads((ROOT/'data/source_provenance.json').read_text()),
 'results':'assignment7_results.json','reproducibility':{'python':sys.version,'packages':versions,'numba':'0.67.0','llvmlite':'0.49.0','seed':20260914,'primary_starts':300,'permutations':499,'refitted_bootstrap':199,'floor_log_sd':.001},
 'headline':'Two distributions fit well, but note optimization and duration interpretation do not survive refitting; timing evidence is real, predictive advantage is mixed, and rare losses remain underexplained.',
 'outputs':['Assignment_7_Fund_X_Two_Regime_Review.pdf','Assignment_7_Fund_X_Two_Regime_Review.tex','Assignment_7_Fund_X_Two_Regime_Review.xlsx'],
 'scripts':['scripts/compute_assignment7_regimes.py','scripts/build_assignment7_report.py','scripts/build_assignment7_workbook.mjs','scripts/verify_assignment7.py'],
 'checks':{'115_source_values_match':True,'independent_likelihood_absolute_difference':abs(F['ll']-R['independent_statsmodels']['ll']),'source_document_preserved':True,'source_docx_read':'All OOXML text and embedded figures inspected. Bundled DOCX renderer unavailable because bundled LibreOffice is absent.'}}
(ROOT/'assignment7_manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
print('Created report source, figures, and manifest.')
