Project 1 May 2026 update

Main file for Overleaf: Project_1_May2026_Update.tex
Automation script: scripts/update_project1_monthly.py
Use source spartan for the monthly no-touch update. It needs Python, openpyxl, and pymupdf.
Use source workbook if Professor Boyle sends a revised spreadsheet.
Installed local scheduled task: Project1_LSQ_Monthly_Update, monthly on the 10th at 9:00 AM when logged in and plugged in.
For professor self-service downloads, use the GitHub Actions plus Google Drive setup in GOOGLE_DRIVE_AUTOMATION.md.

Refresh from Spartan PDF:
python scripts/update_project1_monthly.py --source spartan --output-dir .

Refresh from workbook:
python scripts/update_project1_monthly.py --source workbook --workbook C:\Users\HP\Downloads\COMBined3a.xlsx --output-dir .

Pipeline test for the next month:
python scripts/update_project1_monthly.py --source spartan --simulate-next-month --output-dir test_next_month