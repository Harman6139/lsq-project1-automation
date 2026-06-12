# Boyle LSQ Workspace

This repository is the live LaTeX and code workspace. Google Drive is the professor-facing delivery folder.

## Current Links

- Drive folder: <https://drive.google.com/drive/folders/1MgFc1OMXcFoTzDgcfpae1n_cKhDuDOzq?usp=drive_link>
- GitHub workspace: <https://github.com/Harman6139/lsq-project1-automation>

## Workflow

- Monthly Project 1 data updates run through GitHub Actions on the 10th of each month.
- The workflow rebuilds the PDF, Excel workbook, LaTeX source, validation files, and Overleaf zip.
- The workflow publishes the current files into Google Drive through the Apps Script upload endpoint.
- Future project files should be committed into this repository and added to `workspace_artifacts.json`.
- The push-triggered publish workflow then updates the Drive folder without manual zipping or transfer.

## Overleaf

The always-current Overleaf import bundle is `Boyle_LSQ_Workspace_Overleaf_Latest.zip` in the Drive folder.

Overleaf cannot be treated as the reliable automated source of truth unless its paid Git/GitHub sync is connected. If that is available, this repository should be the source repo connected to Overleaf.
