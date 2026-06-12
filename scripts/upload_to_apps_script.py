from __future__ import annotations

import argparse
import base64
import json
import mimetypes
import os
import urllib.request
from pathlib import Path


DEFAULT_UPLOADS = [
    ("Project_1_May2026_Update.xlsx", "Project_1_LSQ_Monthly_Update.xlsx"),
    ("Project_1_May2026_Update.pdf", "Project_1_LSQ_Monthly_Update.pdf"),
    ("Project_1_May2026_Update.tex", "Project_1_LSQ_Monthly_Update.tex"),
    ("Harman_Boyle_Project1_May2026_Overleaf_Update.zip", "Harman_Boyle_Project1_Overleaf_Latest.zip"),
    ("manifest.json", "Project_1_LSQ_Monthly_Update_manifest.json"),
]


def build_payload(project_dir: Path, secret: str) -> dict[str, object]:
    files = []
    for local_name, drive_name in DEFAULT_UPLOADS:
        local_path = project_dir / local_name
        if not local_path.exists():
            raise SystemExit(f"Missing expected file: {local_path}")
        mime_type = mimetypes.guess_type(drive_name)[0] or "application/octet-stream"
        files.append(
            {
                "name": drive_name,
                "mimeType": mime_type,
                "contentBase64": base64.b64encode(local_path.read_bytes()).decode("ascii"),
            }
        )
    return {"secret": secret, "files": files}


def main() -> None:
    parser = argparse.ArgumentParser(description="Upload Project 1 files through a Google Apps Script web app.")
    parser.add_argument("--project-dir", type=Path, default=Path.cwd(), help="Folder containing generated Project 1 files.")
    parser.add_argument("--web-app-url", default=os.environ.get("APPS_SCRIPT_WEB_APP_URL", ""), help="Apps Script web app URL.")
    parser.add_argument("--secret", default=os.environ.get("APPS_SCRIPT_UPLOAD_SECRET", ""), help="Shared upload secret.")
    parser.add_argument("--dry-run", action="store_true", help="Print planned uploads without contacting Apps Script.")
    args = parser.parse_args()

    project_dir = args.project_dir.resolve()
    if args.dry_run:
        for local_name, drive_name in DEFAULT_UPLOADS:
            local_path = project_dir / local_name
            if not local_path.exists():
                raise SystemExit(f"Missing expected file: {local_path}")
            print(f"DRY RUN: {local_path} -> Google Drive as {drive_name}")
        return

    if not args.web_app_url:
        raise SystemExit("Missing Apps Script web app URL. Set APPS_SCRIPT_WEB_APP_URL.")
    if not args.secret:
        raise SystemExit("Missing upload secret. Set APPS_SCRIPT_UPLOAD_SECRET.")

    body = json.dumps(build_payload(project_dir, args.secret)).encode("utf-8")
    request = urllib.request.Request(
        args.web_app_url,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=120) as response:
        result = json.loads(response.read().decode("utf-8"))
    if not result.get("ok"):
        raise SystemExit(f"Apps Script upload failed: {result}")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
