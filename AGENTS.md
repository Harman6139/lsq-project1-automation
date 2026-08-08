# Professor Boyle Research Workspace

## Scope

These instructions apply to this repository and all Professor Boyle deliverables maintained from it.
Read this file before handling a new instruction document, dataset, monthly update, or professor response.

## Canonical Sources

- Live repository: `codex_project1a_context/project1_may2026_deliverables`
- GitHub: `https://github.com/Harman6139/lsq-project1-automation`
- Professor-facing Drive: `https://drive.google.com/drive/folders/1MgFc1OMXcFoTzDgcfpae1n_cKhDuDOzq`
- `workspace_artifacts.json` controls which repository files are published to Drive and their folder names.
- GitHub is the source of truth for LaTeX, code, data provenance, and reproducibility.
- Drive is the source of truth for clean, viewer-ready professor deliverables.

Treat these sibling directories as historical archives unless a task explicitly names them:

- `codex_project1a_context/final_deliverables`
- `codex_project1a_context/assignment2_deliverables`
- `codex_project1a_context/overleaf_project_bundle`
- directories whose names contain `test`, `extracted`, or `reply`

Do not update or publish from an archive when a corresponding file exists in this repository.

## Project Registry

### Project 1: Monthly Paper Update

- Purpose: update Fund X, S&P 500 Total Return, NVIDIA, performance statistics, Tables 2 and 4, alpha/beta, serial-correlation diagnostics, Newey-West inference, and MPPM.
- Live report files remain at the repository root as `Project_1_May2026_Update.*`; the stable Drive names begin with `Project_1_LSQ_Monthly_Update` even though the sample advances.
- Inputs and outputs use `data/`, `tables/`, `isolated_excel/`, and `scripts/update_project1_monthly.py`.
- The scheduled GitHub workflow runs at 13:00 UTC on the 10th, 15th, 20th, and 25th of each month. Later attempts allow for a delayed Fund X release.
- Drive destination: `Project Monthly Update`. Isolated tables go in its `Excel Tables`, `Return Series`, and `Data Reconciliation` subfolders.
- Do not change the established Assignment 1 report format unless the user explicitly asks.

### Assignment 2: Leveraged S&P 500

- Location: `workspace/assignment_2`
- Purpose: apply leverage parameter lambda to monthly S&P 500 Total Return returns and calculate return statistics, Sortino ratios, and Omega ratios.
- Primary script: `scripts/compute_assignment2_leveraged_sp500.py`.

### Assignment 3: Statistical Integrity Tests

- Location: `workspace/assignment_3`
- Purpose: assess possible smoothing or manipulation using the Wald-Wolfowitz runs test, Bollen-Pool checks, serial dependence diagnostics, and the bias ratio.
- The established zero-threshold runs test uses the exact conditional distribution because Fund X has very few negative months.
- Additional assumption-aware checks include an exact local zero-band test and a circular block bootstrap.
- Primary script: `scripts/compute_assignment3_integrity_tests.py`.

### Assignment 4: q-Factor Analysis

- Location: `workspace/assignment_4`
- Purpose: estimate q and q5 factor regressions for Fund X excess returns, with Newey-West inference, bootstrap and influence checks, parameter-stability tests, and 48-month rolling q5 alpha.
- Primary script: `scripts/compute_assignment4_qfactor.py`.

## Efficient Linkage Check

For a new document or professor concern, do not reread every prior PDF.

1. Read the new instruction or review document completely, including tables, footnotes, comments, and tracked changes.
2. Identify the topic and sample endpoint. Map it to the Project Registry above.
3. Search only the relevant assignment using `rg` for distinctive terms, statistics, formulas, or table names.
4. Read, in order, the relevant manifest, LaTeX section, computation function, and source data. Open the full prior PDF or workbook only when formatting or a calculation chain requires it.
5. Use `git log -S"distinctive phrase"` or `git log -- <path>` only when authorship or version history matters.
6. Recompute disputed values independently. Do not accept a document's verdict because its numbers resemble earlier work.
7. State whether the new item reproduces, extends, contradicts, or is unrelated to prior work.

Always distinguish:

- the economic hypothesis from the generic statistical null;
- one-sided from two-sided alternatives;
- exact from asymptotic p-values;
- unconditional frequency tests from tests conditional on observed counts;
- evidence consistent with an explanation from evidence that identifies that explanation;
- the sample used in the paper from later monthly samples.

## New Assignment Structure

Create future assignments under `workspace/assignment_N` using the next assignment number. Use this structure as needed:

```text
workspace/assignment_N/
  Assignment_N_Descriptive_Name.pdf
  Assignment_N_Descriptive_Name.tex
  Assignment_N_Descriptive_Name.xlsx
  scripts/
  data/
  tables/
  figures/
  assignmentN_manifest.json
```

- A PDF and LaTeX source are standard.
- Add an Excel workbook when calculations are tabular or the professor may want to inspect them.
- Keep computation scripts and exact input data sufficient to reproduce every reported number.
- Put CSV tables and figures in their subfolders rather than beside the main deliverables.
- Keep manifests in GitHub only.
- Do not create zip bundles unless the user explicitly requests one.

## Calculation Standards

- Verify dates, observation counts, units, missing values, ties, thresholds, return definitions, and annualization before running tests.
- Fund X returns come from the documented Fund X source. S&P 500 uses the total return index series. NVIDIA uses adjusted close. Record source URLs and reconciliation results where applicable.
- Preserve full precision in calculations and round only for presentation.
- For small or imbalanced groups, prefer an exact distribution when available. Do not present a normal approximation as authoritative when its conditions fail.
- Match each p-value to the stated alternative. Report the statistic, reference distribution, tail, conditioning, and sample size.
- Account for serial dependence with an appropriate method such as Newey-West inference or a block bootstrap when the estimand and test permit it.
- Treat robustness checks as sensitivity evidence, not automatic proof of a causal explanation.
- Independently reproduce high-impact results with a second implementation or library where practical.

## Document And Workbook QA

- Match the original paper's restrained LaTeX style for paper-facing tables and reports.
- Keep headings with their tables or figures on the same page.
- Use concise human prose addressed to Professor Phelim Boyle.
- Do not use em dashes.
- Do not add AI references, process narration, or unsupported certainty to professor-facing files.
- Compile every final `.tex` file and visually inspect every PDF page for clipping, overlap, bad page breaks, and missing assets.
- Render and inspect every created or edited DOCX before delivery.
- Check every workbook for formula errors, broken references, inconsistent units, missing rows, and presentation problems.
- Confirm generated statistics against the manifest and source tables before publishing.

## Publishing Workflow

1. Finish and validate local outputs in the live repository.
2. Add professor-facing artifacts to `workspace_artifacts.json` with a human-readable Drive name and correct folder path.
3. Keep Drive folders named `Project Monthly Update`, `Assignment 2`, `Assignment 3`, `Assignment 4`, and so on. Never prefix them with `02`, `03`, or similar numbering.
4. Keep `Monthly Automation` limited to the script that performs the recurring monthly update.
5. Do not upload README files, manifests, zip files, QA renders, internal notes, credentials, or temporary files to Drive.
6. Commit and push the intended repository changes. Confirm the GitHub workflow succeeds and the Drive files were replaced or created in the correct folders.
7. Do not rename a stable automated Drive artifact merely because its sample endpoint advanced.

## Default Professor Package

Unless the professor requests something different:

- Attach the viewer-ready PDF and the main Excel workbook.
- If he requests isolated tables, attach the requested isolated Excel files instead of making him extract sheets.
- Put the Google Drive workspace link and the relevant GitHub assignment link in the email body.
- Do not attach LaTeX source, scripts, raw data, figures, manifests, or zip files when the links already provide them, unless he explicitly requests those files.
- Keep the email polite and concise. State what changed, the data source and validation performed, the main result and caveat, the attachment names, and the two workspace links.

## Security And Cleanliness

- Never place API keys, service-account JSON, tokens, passwords, cookies, or private credentials in Git, Drive, reports, manifests, or this file.
- Use configured GitHub secrets and the existing Drive publishing endpoint without printing secret values.
- Ignore temporary QA folders and local downloads when publishing.
- Before committing, inspect `git status` and preserve unrelated user changes.
