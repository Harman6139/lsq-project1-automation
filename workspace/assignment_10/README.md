# Assignment 10: return-screening frontiers

The current note, `Return_Screening_Frontier.pdf`, explains the full comparison of
38 ways of combining four checks across ten reporting changes. The unsent email
draft has 248 words. The one-page note is archived in
`History/20261119_One_Page_Handoff`. Earlier three-page versions are in Git
history and the University History folder.

`figures/reporting_matrix_appendix.pdf` contains the 38-by-10 counts, differences
against the original and newer pairs, and a separate frontier for every edit.
`figures/reporting_matrix_top_quintile.pdf` keeps the same pooled cutoffs for the
39 highest-Sharpe portfolios. The underlying CSVs are:

- `tables/all_reporting_comparison.csv`: 38 arrangements by ten edits, with
  original, edited and new warning counts and differences from both pairs.
  Includes the 1%, 5% and 10% older-data cutoffs and all three groups.
- `tables/all_reporting_matched_counts.csv`: comparisons holding the observed
  warning cap fixed, with achieved original warnings and the cutoff used.
- `tables/all_reporting_frontiers.csv`: best observed coverage by edit over
  all 38 arrangements and over each of the two benchmark pairs.
- `tables/all_reporting_joint_curves.csv`: average and worst coverage with one
  arrangement and one cutoff across all ten edits.
- `tables/all_reporting_summary.csv`: average coverage, worst coverage and
  edit-by-edit wins or ties at the pooled older 5% target.

Reproduce with `python scripts/compare_all_reporting.py`,
`python scripts/build_methods_report.py`, `python scripts/plot_reporting_matrix.py`
and XeLaTeX for the note. The expanded curves use the original 101 historical
cutoffs and the same observed histories and saved design, including the
identical seeded mask for the half-loss edit. They require no new simulations
or calibration. The replay matches 3,420 existing point rows and 30,704
existing curve rows in all count fields. `data/all_reporting_comparison.json`
records the checks, source hashes and results.

The later-sample envelopes show which arrangement and cutoff were best on a
given edit or under the stated summary and cap. They are descriptive. The
earlier choice among arrangements was based on three edits and older data.
The original two-curve figure and workbook remain available as earlier views.
Correspondence, personal download inventories and restricted originals stay local.

The supplied portfolio appendix's implementation is mapped in
`research/proposal_implementation_audit.json`. Its core empirical exercises were
run in Assignment 9, and Assignment 10 extends the choice of checks. Alpha and
t-statistics were calculated, while separate selection exercises ranked by those
statistics and a new matched simulation-versus-empirical study remain unrun.

The original analysis release is pinned at
`ffbc7598df5feb6fc9de40e200521727db2c89e0`. The current PDF replaces the existing
Drive report through the scoped publisher. The publisher recreates stored artifacts;
current IDs and byte-for-byte raw readback are recorded in the evidence file. Publication evidence is in
`data/publication_readback.json`; archived evidence describes the one-page release.

## Economic question and findings

The initial Assignment 9 extension found one conventional warning among 195
unchanged factor histories. In the 194-strategy core, a higher cutoff reduced
three-month delayed-loss warnings from 111 to 66 while baseline warnings went
from one to zero. This is the familiar cost of raising a warning threshold.

The new question compares types and numbers of checks for a given warning burden.
It uses four one-sided scores: bias ratio, fitted-normal loss deficit, positive
lag-one dependence, and a local four-bin contrast around zero. There are 26
primary OR/strict-majority configurations and 12 fixed mean-rank/PCA comparators.
These are chosen benchmark families, not every available return diagnostic.

At a 5% older-reference allowance, the original two-score combination warns on
104 of 194 US delayed-loss records and 3 smoothed records, with one baseline
warning. The local/serial pair gives 192 and 189, with three baseline warnings.
On the world-factor source the corresponding counts are 79 and 5, with six
baseline warnings, versus 152 and 153, with three. These are total alerts on
altered records; newly triggered alerts are stored separately.

The overall older-data winner is OR:B+A+Z (checks1+3+4); the best pair is
OR:A+Z (checks3+4), with an almost identical training score. These choices perform similarly
on ordinary later factor histories. However, in the first published-test block
of the author-released Chenâ€“Pelgerâ€“Zhu portfolio, the local/serial pair misses a
four-loss reporting change that adding the bias check catches. The original
bias/loss-count pair also catches that example: a third check is not universally
required. This is a particular counterexample to that pair's universal usefulness,
not proof that performance itself determines the optimal number of checks.

The initial CPZ block has monthly excess Sharpe 1.525, subsequent disjoint block
0.475, final overlapping 108-month block 0.380, and full published 300-month test
0.749. The source is a gross historical model test, not a live net fund NAV.
Three real net NAV records and 153 world factors were also obtained; their
performance does not itself match Fund X's risk-adjusted range.

## Frozen design and chronology

`data/frozen_design.json` was written before inspecting new screening outcomes.
The earlier runtime pilot discarded all score outcomes. Performance summaries
were used to judge whether candidate external sources cover Fund X's range.
The external input hashes were locked separately before screening those sources.

- Primary development: 1980â€“2004; calibration: 2005â€“2016; evaluation: 2017â€“2025.
- Cohort: 194 complete CZ factors; 108 months primary, 60-month rolling December
  endpoints as sensitivity; original and forced-value stock weights; spread and
  explicitly cash-funded versions.
- Development uses complete December-ending windows. Each marginal diagnostic
  is mapped to a fixed historical percentile; these ranks are not p-values.
- Every full combination has its own conservative cutoff. Strict exceedance
  never splits tied scores. The 0% and 100% endpoints are investigate-none/all.
- Null reference resampling uses joint calendar blocks of 12 months, with
  6-month sensitivity. All strategy columns move together.
- Combination selection uses old calibration reporting changes only, maximising
  average *new* warnings for three declared training policies. The equal policy
  weights define a reference objective, not an estimated fraud prevalence.
- Five strategy folds hold complete economic categories together. All maps,
  PCA loadings, cutoffs and selection are fitted excluding the held-out categories.
- A9 had already examined 2017â€“2025 descriptions and two-score results. This is
  a new frozen comparison, not a claim that the historical test period was virgin.

External CPZ reference maps use 1926â€“1979 and calibration uses 1980â€“1991, before
the whole author-designated 1992â€“2016 test. We evaluate the first two disjoint
108-month blocks, the final overlapping 108-month block, and all 300 test months.
The 300-month bootstrap reference resamples only 144 observed calibration months;
it is a conditional historical extrapolation, not 300 additional observed months.
Same-date CZ reference records show the older calibration's later drift.

## Scores, policies and frontiers

The local score cancels a smooth linear density slope. With b=.25 sample SD,
let L2 count [-2b,-b), L1 [-b,0), G1 (0,b], G2 (b,2b]. The score is
`[3(G1âˆ’L1)âˆ’(G2âˆ’L2)] / sqrt[9(G1+L1)+G2+L2]`, zero if its denominator is zero.
Exact zeros are counted separately. It is empirically calibrated, not an exact
normal test or the original pooled Bollenâ€“Pool procedure. Bandwidth .5 SD is a
prespecified sensitivity.

The main loss policy replaces losses within .25 of each path's sample SD with
a gain of .0125 SD. Hidden amounts are never recognised or recognised after
1, 3 or 6 months. A half-application policy and the earlier fixed 1% bound are
sensitivities. Incoming recognition cannot be hidden again. The spread ledger
conserves additive P&L after settlement; funded sensitivity conserves log NAV.
Actual six-month prehistories initialise observed records. Bootstrap prehistory
is taken from the actual six months preceding the first sampled calendar month.
No missing return observations are filled or fabricated. Fund X has baseline
application only because pre-2017 months were not supplied.

The symmetric one-lag filter is a separate reporting sensitivity. It directly
induces serial dependence; its profit-sum change is reconciled to its endpoints.
Likewise, fixed tiny-positive replacement gains directly create local bunching.
The strong A and Z results partly follow from these declared alternatives.
Delay lengths and application probabilities vary severity and timing, not an
entirely unknown manipulation family.

Full curves plot actual unchanged warning rates against *total* altered-record
warning rates. New alerts are a separate optimisation/diagnostic measure and
need not be monotone across the full budget range. The best-looking final-data
envelope is descriptive. Deployable combination choices are frozen using old data.
Top-quintile groups retain original underlying Sharpe rankings after alteration;
pooled cutoffs do not match warning budgets within each subgroup. Selection
sensitivity likewise fixes winner weights from original rather than altered h.

Paired uncertainty uses 500 joint-calendar resamples with fixed old choices.
The simultaneous band covers 38 comparisons within each mechanism/group/budget
cell, not every cell jointly. There is no independent-binomial treatment of factors.

## Data provenance and rights

`data/source_provenance.json` preserves the pinned October 2026 CZ release and
exact source hashes. Existing public input data are frozen in `data/raw`.
The raw external files, licensed/distribution-restricted fund PDFs and research
paper downloads stay local and are excluded from Git. Acquisition URLs, source
definitions, hashes and licences are in `research/external_provenance.json`,
`research/data_search.json` and `research/provenance_inventory.json`.

The author data page is <https://mpelger.people.stanford.edu/data-and-code>.
CPZ's main factor uses monthly L1-normalised stock weights, gross notional1,
and is an excess payoff. CZ and JKP long/short books have gross notional2.
Never subtract RF from these excess payoffs a second time. Risk-relative reporting
changes avoid making the loss bound depend on an arbitrary notional scale.
The NAV sources are published net USD returns. Their monthly cells were extracted
with two libraries and all annual totals reconciled within rounding bounds.

JKP is a separate global source but overlaps CZ in stocks and factor concepts.
Live NAVs do not form a representative manager sample. No fraud-labelled cases,
actual fraud prevalence or monetary investigation benefits were obtained.

## Closest work and significance

`research/literature_review.json` compares 18 studies and records primary URLs,
inspection coverage and version gaps. Bollenâ€“Pool already combines return flags
and compares warning budgets; JoenvÃ¤Ã¤rÃ¤â€“Kosowski aggregates statistics; GonzÃ¡lez
and colleagues study strong performers; Beneishâ€“Vorst compares investigation costs.
The score combination, frontier, and basic detection-versus-warning tradeoff are
not new methods. The possible increment is new, consequential evidence about
where fixed screening choices transfer or fail. A substantial advance for Risk
Sciences is not established merely by completing this experiment.

## Reproduction and checks

From this directory, with Python3.11, numpy/pandas/scipy/pyarrow and matplotlib:

```text
python scripts/verify_frontier_independent.py
python scripts/run_frontier.py --stage core --weighting original
python scripts/run_frontier.py --stage core --weighting value_weighted
python scripts/run_frontier.py --stage folds
python scripts/run_frontier.py --stage uncertainty
python scripts/run_external_validation.py
python scripts/run_sensitivity.py
python scripts/summarize_results.py
python scripts/plot_frontiers.py
python scripts/build_methods_report.py
xelatex -interaction=nonstopmode -halt-on-error Return_Screening_Frontier.tex
```

The report builder reads `scripts/methods_note_body.tex` and frozen CSVs; it does
not rerun the backtest. `build_handoff.py` reproduces the archived short note.

Retain the frozen design rather than rerunning `freeze_design.py`. Fetch external
inputs from the recorded URLs and match hashes before external validation. The
extraction code is in `research/extract_external_returns.py`. Score caches are
regenerable and excluded from Git; they refuse changed source/code/design hashes.
The assignment's `.gitattributes` prevents line-ending changes to frozen bytes.

Independent verification covers all four scores, percentile ties, OR/majority
votes, PCA against SVD, conservative weighted cutoffs, both reporting ledgers,
pending settlement, and calendar prehistories. The 570 main handoff-related output
rows and the critical global/exceptional-source comparisons were recomputed
separately. Details are in `data/independent_verification.json`.

Main numerical jobs took about109s,119s,18s,8s,44s and17s: approximately5.3minutes
in total, with parallel execution where independent. CPU26 was not needed.
Current remote institutional access could not be confirmed; no heavy remote
backtest was attempted. The timing estimate concerned numerical computation,
not literature review or report preparation.
