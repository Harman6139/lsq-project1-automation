# Assignment 9: Chen–Zimmermann screening

The professor-facing files are `Assignment_9_Chen_Zimmermann_Screening.pdf` and
`Assignment_9_Chen_Zimmermann_Screening.xlsx`. The matching report source is the
`.tex` file. This release is dated 11 November 2026.

The PDF and workbook are published in the established Drive workspace's
Assignment 9 folder. Both uploaded raw files were downloaded again and matched
byte for byte. The analysis release is pinned at GitHub commit
`e4894d8c233ee75b9b35d1f3bf9d5d415e5dea96`; publication evidence is in
`data/publication_readback.json`. Only the dedicated Assignment 9 publisher ran.

## Findings

The 2017–2025 common window has 195 complete individual factor records. One
original-construction long–short spread warns under either conventional screen;
four funded records warn. Forced stock value weighting produces no warnings in
this window. The common calibration/evaluation cohort has 194 names.

Selection effects depend on the search size and review window. They need not
increase as the investor searches more strategies. The strongest full-pool
108-month record is not flagged. No individual factor reaches Fund X's excess
Sharpe range. A separately declared exploratory funded combination approaches
its zero-rate ratio, but has far lower mean return and excess Sharpe.

The main reporting exercise hides underlying losses no larger than 1%, initially
reports a 0.05% gain, and deducts the hidden amount after three months. Conventional,
ordinary-reference and selection-reference rules warn on 120, 111 and 66 out of
194 paths, respectively. Baseline counts are 1, 1 and 0. This is a conditional
detection comparison for specified reporting policies, not validation against
known fraudulent funds. The stricter cutoff has a material detection cost.

The 5% calibration target does not transfer uniformly: the full-pool forced-value
60-month held-out bootstrap warning frequency is 9.4%. These findings strengthen
an empirical qualification of return screens. A substantial new statistical
method or a general limit applying to all spectacular-return funds is not shown.

## Data and interpretation

- Official October 2026 Open Source Asset Pricing aggregate portfolio returns,
  pinned at Hugging Face dataset commit
  `dd1054254c4501776432caa6d7ce5ecd9586f6a9`.
  Source: <https://www.openassetpricing.com/data/>.
- 212 predictor long–short factors; dates through December 2025 despite the
  October 2026 release label. Original-paper constructions are primary. The
  forced-value-weighted file retains the original sorts.
- The data are published reconstructed stock-strategy returns, not live
  hedge-fund NAVs. All 195 complete evaluation strategies were published by 2016.
  Updated stock data and selection of the published-factor catalogue remain
  retrospective. Source returns are gross of implementation and management costs.
- Published percentages are divided by 100 exactly once. No imputation,
  winsorisation, mean shifts, or added economic returns are used.
- A long–short spread is already an excess payoff; do not subtract RF a second
  time. The explicit funded sensitivity is RF + LS per unit of equity, one unit
  long and one unit short, with cash collateral earning RF and no borrowing cost.
- Fund X's frozen January 2017–September 2026 series matches the current outer
  paper package. Comparisons use January 2017–December 2025 only. Fund X is net
  reported; factors are reconstructed gross returns.
- French monthly RF and FF3 come from the official Kenneth French Data Library.
  Its risk-free source changes in June 2024.

`data/source_provenance.json` stores exact download URLs, licence information and
hashes. The original professor ZIP and note are preserved locally in `source/`,
which is excluded from the public repository. The
current manuscript is the **outer** `source/paper_package/main.tex`, titled
*The Limits of Return-Based Due Diligence*. The nested older paper ZIP/PDF is
historical and must not be treated as the current manuscript.

## Design

`data/frozen_design.json` fixes development (1980–2004), calibration (2005–2016),
evaluation (2017–2025), cohorts, random seeds, 108/60-month records, block lengths
and reporting policies. Its predecessor and the pre-outcome audit amendment
adding K=5 and K=50 are retained. Do not run `freeze_design.py` over this release
to change its design after looking at results.

`data/exploratory_combination_design.json` explicitly records that combinations
were added after the individual-factor support gap was observed, but before any
combination outcomes were evaluated. Weights use 2005–2016 only and stay fixed.
They are not assigned the cutoffs learned for individual strategies.

Selection probabilities average exactly over size-K subsets without replacement.
Joint circular calendar-block resampling retains cross-strategy dependence.
Percentile score maps are not p-values. The normal loss count is the paper's
Gaussian adaptation, not the original pooled Bollen–Pool statistic. The two
conventional rules are bias ratio >2 and fitted-normal lower-tail p<0.05.

`data/locked_cutoffs.json` retains the exact binary64 values and strict `>` rule.
When reading cutoff CSVs, use pandas `float_precision='round_trip'`; its default
parser changes some values by one or two units in the last binary place and
can move tied scores across strict cutoffs. Do not round before decisions.

## Reproduction

Python 3.11 with numpy, pandas, scipy, statsmodels, pyarrow, requests, matplotlib
and PyMuPDF is sufficient for numerical analysis, plotting and PDF rendering.
The workbook uses the bundled artifact-tool Node runtime. XeLaTeX with
Times New Roman compiles the report. Run from this folder:

```text
python scripts/run_descriptive.py
python scripts/run_benchmarks.py --weighting original
python scripts/run_benchmarks.py --weighting value_weighted
python scripts/run_reporting_analysis.py
python scripts/run_exploratory_combinations.py
python scripts/plot_results.py
python scripts/build_report.py
python scripts/verify_assignment9.py --benchmarks --workbook
python scripts/verify_reporting_independent.py
xelatex -interaction=nonstopmode -halt-on-error Assignment_9_Chen_Zimmermann_Screening.tex
xelatex -interaction=nonstopmode -halt-on-error Assignment_9_Chen_Zimmermann_Screening.tex
```

The frozen data, maps and completed reporting ledger are retained. Regenerable
score caches are retained locally and excluded from GitHub. Run both benchmark
runners before benchmark verification on a new checkout. Runners verify dependencies
before reuse; a completed matching reporting
run exits without recomputation. For a genuinely clean rerun, work on a copy and
remove only generated score/map caches and `data/reporting_execution.json` there.
Retain frozen inputs, design and cutoffs, and compare recomputed cutoffs at full
precision. Do not substitute a newer live RF download in this release. Acquisition
can redownload pinned portfolio files if absent; its checked Fund X copy makes
reproduction independent of Assignment 8's location.

The assignment's `.gitattributes` disables line-ending conversion, preserving the
byte hashes of raw CSVs, frozen designs and code across checkouts.

Initial production code hashes and code-history copies retain execution provenance.
The later cache-guard change adds input hashes and does not change numerical
functions. Its comparison and independent results are recorded in
`data/cache_guard_upgrade.json` and `data/independent_verification.json`.

The two principal calibration runs took approximately 66 and 72 seconds, and the
reporting-policy run took approximately 88 seconds locally. None exceeded the
user's ten-minute threshold for using CPU26; no remote access was needed.

## Checks and deliverables

Independent calculations check all 720 observed subset-selection rows, 96
full-precision cutoff values, 960 reporting rows and 240 selected-record policy
rows. Source wide and long LS values and missingness agree exactly. Funding
support, dates, units, publication years, missingness, ties, selection weights,
boundary ledgers and scheduled settlement are checked. Maximum independent
ledger reconciliation error is approximately 1.0e-16.

The six-sheet workbook was audited against all exported CSV cells and all 7,368
formulas, with an input perturbation/recalculation/restoration check and 18 rendered
regions. Native Excel was not opened. The report was compiled and every page
visually inspected; evidence is recorded in the manifest. Temporary QA material
is not part of the professor package. A compact frozen mapping/formula record in
`data/workbook_build_checks.json` permits independent OOXML verification without
the local image renders. Rebuilding the workbook requires the bundled artifact-tool
Node package resolved from `.qa_assignment9/runtime/package.json`, as in the current
workspace, then running `scripts/build_assignment9_workbook.mjs` with that runtime.

The original inputs, numerical tables and scripts are retained for reproduction.
There are no extra real fund histories or verified manager-fraud labels. An
unmodified reconstructed strategy is not a labelled honest fund. Bootstrap ranges
are conditional historical variation, and policy-draw standard errors describe
only reporting-policy randomness on the fixed observed paths.
