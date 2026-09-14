# Assignment 7

This reviews the September 2026 Fund X two-regime note on the fixed January 2017 to July 2026 sample. The original Word document is preserved under `source/`. The PDF and Excel workbook are the professor-facing outputs.

## Reproduce

Use Python 3.11 or later with the versions recorded in `assignment7_manifest.json` (NumPy, pandas, SciPy, statsmodels, numba, llvmlite, matplotlib, pypdf, and openpyxl). From this assignment directory:

```powershell
python scripts/compute_assignment7_regimes.py
python scripts/build_assignment7_report.py
pdflatex -interaction=nonstopmode -halt-on-error Assignment_7_Fund_X_Two_Regime_Review.tex
pdflatex -interaction=nonstopmode -halt-on-error Assignment_7_Fund_X_Two_Regime_Review.tex
node scripts/build_assignment7_workbook.mjs
python scripts/verify_assignment7.py
```

The workbook builder uses the Codex bundled Node runtime and `@oai/artifact-tool`. Make that package available to the builder using a local ignored `scripts/node_modules` junction to the bundled package directory. It reads the saved CSV tables directly. Model fits are saved estimates; editing Excel data does not refit the hidden-state model. Scalar Excel calculations do recalculate.

The primary model uses stationary initial probabilities, six parameters, a 0.001 log-standard-deviation floor, and 300 starts. Monte Carlo ordering tests use 499 permutations; predictive-innovation diagnostics use 199 model simulations with refitting. Seeds and complete results are saved. Episode sensitivity treats removed returns as missing emissions while preserving the calendar transitions.

The source factsheet snapshot is fixed, not a newly downloaded current factsheet. July is estimated. The original note's stated COMBined3b.xlsx was unavailable, so its aggregate claims were checked against the canonical CSV and all 115 CSV returns were independently reconciled to the snapshot PDF.

QA renders and temporary dependency files are excluded from Git and Drive. The supplied DOCX was read through all OOXML text and its three embedded images; its bytes were not edited. The bundled DOCX renderer could not run because bundled LibreOffice is absent. The newly authored LaTeX PDF and workbook were rendered and inspected separately.
