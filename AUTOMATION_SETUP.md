# Project 1 Monthly Automation

This package has two automation options.

## Best option: GitHub scheduled run plus Google Drive publishing

This requires no server from you. GitHub runs the update every month, commits the newest PDF, Excel workbook, LaTeX files, data, and Overleaf zip back to the repository, and can upload the latest files into a shared Google Drive folder.

Steps:

1. Create a private GitHub repository.
2. Upload this `project1_may2026_deliverables` folder into the repository.
3. Make sure GitHub Actions is enabled.
4. Open the `Monthly Project 1 Update` workflow and click `Run workflow` once to test it.

After that, it runs on the 10th of each month at 13:00 UTC. The workflow downloads Spartan's live LSQ PDF, parses the monthly returns, pulls S&P 500 TR and NVIDIA returns from Yahoo Finance, rebuilds the tables, compiles the PDF, updates the Overleaf zip, and uploads stable filenames to Google Drive if the Drive secrets are configured.

For the Google Drive setup, see `GOOGLE_DRIVE_AUTOMATION.md`.

## Local no-hosting option: Windows Task Scheduler

This runs on the local Windows machine once per month. It does not require GitHub, but the computer must be on, plugged in, and logged in as this Windows user at the scheduled time.

Steps:

1. Right-click `Install_Monthly_Automation.ps1`.
2. Choose `Run with PowerShell`.
3. The task will run monthly on the 10th at 9:00 AM when this Windows user is logged in.

For a manual refresh, double-click `Run_Project1_Update.bat`.

The installed task name is `Project1_LSQ_Monthly_Update`. It writes a run log to `automation_last_run.log`.

## Next-month test mode

The script has a self-test mode for checking whether the pipeline advances to the next month:

`python scripts/update_project1_monthly.py --source spartan --simulate-next-month --output-dir test_next_month`

This uses dummy returns for the next month and labels the output as a simulation. It is only a pipeline test. It should not be treated as a real update until Spartan publishes the next monthly LSQ PDF.

## Dependencies

The automation only uses:

- `openpyxl`, for Excel output
- `pymupdf`, for reading the Spartan PDF table

The S&P 500 TR and NVIDIA data are pulled directly from Yahoo Finance. The LSQ data are pulled from Spartan's monthly PDF:

`https://spartanfunds.ca/wp-content/uploads/2021/11/LSQ-Oct21.pdf`
