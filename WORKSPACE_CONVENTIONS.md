# Boyle Project Workspace Conventions

This repository is the working source for Professor Boyle deliverables. Keep professor-facing files in Google Drive and keep reproducible source files in GitHub.

## Google Drive Layout

Drive root: `https://drive.google.com/drive/folders/1MgFc1OMXcFoTzDgcfpae1n_cKhDuDOzq`

Use plain folder names:

- `Project Monthly Update`
- `Assignment 2`
- `Assignment 3`
- `Monthly Automation`

For future assignments, add `Assignment N` at the Drive root. Do not use numeric prefixes such as `02 Assignment 2`.

`Monthly Automation` must contain only the script that runs the monthly Project 1 update. Do not put reports, README files, manifests, or zip files there.

Do not upload README files, manifests, zip bundles, or internal notes to Drive unless the professor specifically asks for them. Drive should contain only clean deliverables, data files, and scripts he may need.

## Repository Layout

Use this pattern:

- Project 1 monthly update files stay at the repository root plus `data/`, `tables/`, `isolated_excel/`, and `scripts/update_project1_monthly.py`.
- Assignment deliverables go under `workspace/assignment_N/`.
- Each assignment folder should contain:
  - report PDF
  - report `.tex`
  - Excel workbook if calculations are tabular
  - `scripts/` for computation code
  - `data/` for inputs or exported data
  - manifest JSON only in GitHub, not Drive

## Publishing

`workspace_artifacts.json` is the source of truth for what gets uploaded to Drive and where it lands.

Use:

```powershell
python scripts/publish_workspace.py --project-dir .
```

The GitHub Actions workflow `Publish Workspace` republishes Drive artifacts when tracked project files change. The monthly Project 1 workflow runs on the 10th of each month and republishes the monthly update.

## GitHub And LaTeX

GitHub is the editable source workspace for LaTeX and scripts:

`https://github.com/Harman6139/lsq-project1-automation`

Keep each assignment's `.tex` file in its assignment folder. If an Overleaf mirror is configured through secrets, the workflow may mirror the LaTeX workspace automatically, but GitHub remains the reliable source of truth.

## Naming

Use human-readable file names in Drive and stable names when files are meant to be replaced by automation. Use underscores for local LaTeX source files when that matches the existing code.

Avoid labels such as `draft`, `AI`, `ChatGPT`, `agent`, `manifest`, or `README` in Drive-facing files.
