# Boyle LSQ Workspace

This repository is the live editable LaTeX and code workspace. Google Drive is the professor-facing delivery folder for PDFs, Excel files, data files, and scripts.

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

The reliable source of truth is Git-backed. Professor Boyle can edit the source files directly in GitHub once added as a collaborator.
