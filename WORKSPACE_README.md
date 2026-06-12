# Boyle LSQ Workspace

This repository is the live LaTeX and code workspace. Google Drive is the professor-facing delivery folder for PDFs, Excel files, data files, and scripts.

## Current Links

- Drive folder: <https://drive.google.com/drive/folders/1MgFc1OMXcFoTzDgcfpae1n_cKhDuDOzq?usp=drive_link>
- GitHub workspace: <https://github.com/Harman6139/lsq-project1-automation>
- Overleaf workspace: configure by setting the GitHub Actions secrets `OVERLEAF_GIT_URL` and `OVERLEAF_GIT_TOKEN`.

## Workflow

- Monthly Project 1 data updates run through GitHub Actions on the 10th of each month.
- The workflow rebuilds the PDF, Excel workbook, LaTeX source, validation files, and live LaTeX workspace.
- The workflow publishes the current files into Google Drive through the Apps Script upload endpoint.
- If Overleaf Git is configured, the workflow also pushes the generated LaTeX workspace into the Overleaf project.
- Future project files should be committed into this repository and added to `workspace_artifacts.json`.
- The push-triggered publish workflow then updates the Drive folder and live LaTeX workspace without manual transfer.

## Live LaTeX Workspace

The reliable source of truth is Git-backed. If Professor Boyle wants an Overleaf link, the Overleaf project should be connected as a Git remote through GitHub Actions. Then the Overleaf project opens as a normal workspace and receives automatic updates after monthly runs and future project commits.
