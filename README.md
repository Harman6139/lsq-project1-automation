# Boyle LSQ Live Workspace

This repository is the editable LaTeX and code workspace for the LSQ project updates.

## Main Links

- Viewer-ready files, Excel workbooks, data, and scripts: <https://drive.google.com/drive/folders/1MgFc1OMXcFoTzDgcfpae1n_cKhDuDOzq?usp=drive_link>
- Editable GitHub workspace: <https://github.com/Harman6139/lsq-project1-automation>

## Current Files

- `Project_1_May2026_Update.tex`: current Project 1 monthly update LaTeX source
- `Project_1_May2026_Update.pdf`: current Project 1 monthly update PDF
- `Project_1_May2026_Update.xlsx`: current Project 1 monthly update Excel workbook
- `workspace/assignment_2/Assignment_2_Leveraged_SP500.tex`: Assignment 2 LaTeX source
- `workspace/assignment_2/Assignment_2_Leveraged_SP500.pdf`: Assignment 2 PDF
- `scripts/update_project1_monthly.py`: monthly automation script

## Automation

Project 1 is updated automatically through GitHub Actions on the 10th of each month. The workflow:

1. pulls the latest LSQ monthly return source,
2. updates S&P 500 Total Return and NVIDIA returns,
3. rebuilds the Project 1 PDF, Excel workbook, LaTeX source, and validation files,
4. republishes the current outputs to the shared Google Drive folder.

The publish workflow also runs when project files are updated in this repository.

## Editing

Professor Boyle can edit files directly in GitHub after being added as a collaborator. For small edits, open a `.tex` or script file, click the pencil icon, make the change, and commit it.

For larger edits, press `.` while viewing the repository to open the browser-based GitHub editor.
