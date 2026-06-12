# Apps Script Drive Upload Setup

Use this when the Google Drive folder is in a normal My Drive account. This avoids the service-account storage-quota issue.

## One-time steps

1. Go to `https://script.google.com`.
2. Click `New project`.
3. Delete the starter code.
4. Paste the contents of `apps_script/Code.gs`.
5. Replace `PASTE_UPLOAD_SECRET_HERE` with the value in `apps_script_upload_secret.txt`.
6. Click `Save`.
7. Click `Deploy`.
8. Click `New deployment`.
9. Choose type `Web app`.
10. Set `Execute as` to `Me`.
11. Set `Who has access` to `Anyone`.
12. Click `Deploy`.
13. Authorize the app when Google asks.
14. Copy the Web app URL.

Give the Web app URL to Codex. Codex will add it to GitHub as `APPS_SCRIPT_WEB_APP_URL` and run the workflow.

## How it works

GitHub Actions sends the latest Excel, PDF, LaTeX source, Overleaf zip, and manifest to the Apps Script web app.
The web app writes those files into this Drive folder:

`https://drive.google.com/drive/folders/1MgFc1OMXcFoTzDgcfpae1n_cKhDuDOzq`

The professor uses the same Drive folder link every month.
