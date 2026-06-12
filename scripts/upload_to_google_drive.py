from __future__ import annotations

import argparse
import json
import os
from pathlib import Path


DEFAULT_UPLOADS = [
    ("Project_1_May2026_Update.xlsx", "Project_1_LSQ_Monthly_Update.xlsx"),
    ("Project_1_May2026_Update.pdf", "Project_1_LSQ_Monthly_Update.pdf"),
    ("Project_1_May2026_Update.tex", "Project_1_LSQ_Monthly_Update.tex"),
    ("Harman_Boyle_Project1_May2026_Overleaf_Update.zip", "Harman_Boyle_Project1_Overleaf_Latest.zip"),
    ("manifest.json", "Project_1_LSQ_Monthly_Update_manifest.json"),
]


def drive_query_escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace("'", "\\'")


def build_service(service_account_json: str):
    try:
        from google.oauth2 import service_account
        from googleapiclient.discovery import build
    except ImportError as exc:
        raise SystemExit(
            "Missing cloud upload dependencies. Install with: pip install -r cloud_upload_requirements.txt"
        ) from exc

    info = json.loads(service_account_json)
    scopes = ["https://www.googleapis.com/auth/drive"]
    credentials = service_account.Credentials.from_service_account_info(info, scopes=scopes)
    return build("drive", "v3", credentials=credentials)


def find_existing_file(service, folder_id: str, name: str) -> str | None:
    query = (
        f"name = '{drive_query_escape(name)}' "
        f"and '{drive_query_escape(folder_id)}' in parents "
        "and trashed = false"
    )
    result = (
        service.files()
        .list(
            q=query,
            spaces="drive",
            fields="files(id, name)",
            supportsAllDrives=True,
            includeItemsFromAllDrives=True,
            pageSize=10,
        )
        .execute()
    )
    files = result.get("files", [])
    return files[0]["id"] if files else None


def upload_file(service, folder_id: str, local_path: Path, drive_name: str) -> dict[str, str]:
    from googleapiclient.http import MediaFileUpload

    media = MediaFileUpload(str(local_path), resumable=True)
    existing_id = find_existing_file(service, folder_id, drive_name)
    fields = "id, name, webViewLink, webContentLink"
    if existing_id:
        uploaded = (
            service.files()
            .update(
                fileId=existing_id,
                body={"name": drive_name},
                media_body=media,
                fields=fields,
                supportsAllDrives=True,
            )
            .execute()
        )
        uploaded["action"] = "updated"
        return uploaded

    uploaded = (
        service.files()
        .create(
            body={"name": drive_name, "parents": [folder_id]},
            media_body=media,
            fields=fields,
            supportsAllDrives=True,
        )
        .execute()
    )
    uploaded["action"] = "created"
    return uploaded


def main() -> None:
    parser = argparse.ArgumentParser(description="Upload the latest Project 1 files to Google Drive.")
    parser.add_argument("--project-dir", type=Path, default=Path.cwd(), help="Folder containing generated Project 1 files.")
    parser.add_argument("--folder-id", default=os.environ.get("GOOGLE_DRIVE_FOLDER_ID", ""), help="Google Drive folder ID.")
    parser.add_argument(
        "--service-account-json",
        default=os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON", ""),
        help="Google service account JSON. Prefer passing this as a GitHub Secret.",
    )
    parser.add_argument("--dry-run", action="store_true", help="Print planned uploads without contacting Google Drive.")
    args = parser.parse_args()

    project_dir = args.project_dir.resolve()
    planned = []
    for local_name, drive_name in DEFAULT_UPLOADS:
        local_path = project_dir / local_name
        if not local_path.exists():
            raise SystemExit(f"Missing expected file: {local_path}")
        planned.append((local_path, drive_name))

    if args.dry_run:
        for local_path, drive_name in planned:
            print(f"DRY RUN: {local_path} -> Google Drive as {drive_name}")
        return

    if not args.folder_id:
        raise SystemExit("Missing Google Drive folder ID. Set GOOGLE_DRIVE_FOLDER_ID.")
    if not args.service_account_json:
        raise SystemExit("Missing service account JSON. Set GOOGLE_SERVICE_ACCOUNT_JSON.")

    service = build_service(args.service_account_json)
    results = []
    for local_path, drive_name in planned:
        results.append(upload_file(service, args.folder_id, local_path, drive_name))
    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
