# Google Drive Monthly Publish Setup

This is the lowest-maintenance setup for Professor Boyle.

GitHub Actions runs the update every month. After it rebuilds the Project 1 PDF, Excel workbook, LaTeX source, and Overleaf zip, it uploads the latest files into one Google Drive folder. Professor Boyle only needs the folder link.

## What you create once

1. A private GitHub repository containing this `project1_may2026_deliverables` folder.
2. A Google Drive folder, for example `LSQ Project 1 Monthly Updates`.
3. A Google Cloud service account with a JSON key.
4. One GitHub Secret:
   - `GOOGLE_SERVICE_ACCOUNT_JSON`

## Google setup

1. Go to Google Cloud Console.
2. Create a project.
3. Enable the Google Drive API.
4. Create a service account.
5. Create a JSON key for that service account.
6. Copy the service account email address.
7. In Google Drive, create the output folder and share it with the service account email as `Editor`.
8. Share the same folder with Professor Boyle as `Viewer` or `Editor`.
9. The Drive folder ID is already configured in the workflow:
   `1MgFc1OMXcFoTzDgcfpae1n_cKhDuDOzq`

The folder URL looks like this:

`https://drive.google.com/drive/folders/FOLDER_ID_HERE`

## GitHub setup

In the private GitHub repository:

1. Go to `Settings`.
2. Go to `Secrets and variables`.
3. Go to `Actions`.
4. Add `GOOGLE_SERVICE_ACCOUNT_JSON` with the full JSON key contents.
5. Open the `Monthly Project 1 Update` workflow.
6. Click `Run workflow` once.

After that, it runs monthly.

## Files Professor Boyle will see

The Drive folder will contain stable filenames:

- `Project_1_LSQ_Monthly_Update.xlsx`
- `Project_1_LSQ_Monthly_Update.pdf`
- `Project_1_LSQ_Monthly_Update.tex`
- `Harman_Boyle_Project1_Overleaf_Latest.zip`
- `Project_1_LSQ_Monthly_Update_manifest.json`

Each monthly run updates those same files, so the professor can use the same Drive folder link every month.

## Important note

A simple Google API key is not enough for Drive uploads. The workflow needs a service account JSON key because it is writing files into a Drive folder.
