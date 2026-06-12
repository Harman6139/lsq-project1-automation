from __future__ import annotations

import argparse
import base64
import hashlib
import json
import mimetypes
import os
import urllib.request
from datetime import datetime, timezone
from pathlib import Path


DEFAULT_CONFIG = "workspace_artifacts.json"
INDEX_NAME = "workspace_index.txt"
MANIFEST_NAME = "workspace_manifest.json"


def load_config(path: Path) -> dict[str, object]:
    if not path.exists():
        raise SystemExit(f"Missing workspace artifact config: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def file_digest(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def artifact_paths(project_dir: Path, config: dict[str, object]) -> list[dict[str, str]]:
    artifacts = config.get("artifacts")
    if not isinstance(artifacts, list):
        raise SystemExit("workspace_artifacts.json must contain an artifacts list.")
    normalized = []
    for artifact in artifacts:
        if not isinstance(artifact, dict):
            raise SystemExit("Each artifact entry must be an object.")
        local_path = str(artifact["local_path"])
        drive_name = str(artifact["drive_name"])
        description = str(artifact.get("description", ""))
        group = str(artifact.get("group", "workspace"))
        normalized.append(
            {
                "local_path": local_path,
                "drive_name": drive_name,
                "description": description,
                "group": group,
            }
        )
    return normalized


def write_index(project_dir: Path, config: dict[str, object], artifacts: list[dict[str, str]]) -> None:
    generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    lines = [
        "Boyle LSQ Workspace",
        f"Updated: {generated_at}",
        "",
        f"Drive folder: {config.get('drive_folder_url', '')}",
        f"LaTeX/code workspace: {config.get('github_repo_url', '')}",
        "",
        "Current files in this Drive folder:",
    ]
    for artifact in artifacts:
        lines.append(f"- {artifact['drive_name']}: {artifact['description']}")
    lines.extend(
        [
            "",
            "Monthly automation:",
            "Project 1 runs automatically through GitHub Actions on the 10th of each month.",
            "It rebuilds the PDF, Excel file, LaTeX source, data files, and workspace zip.",
            "",
            "Overleaf note:",
            "The always-current LaTeX bundle is Boyle_LSQ_Workspace_Overleaf_Latest.zip.",
            "If an Overleaf project is needed, import or refresh it from that zip or from the GitHub repo.",
        ]
    )
    (project_dir / INDEX_NAME).write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_manifest(project_dir: Path, config: dict[str, object], artifacts: list[dict[str, str]]) -> None:
    generated_at = datetime.now(timezone.utc).isoformat()
    rows = []
    for artifact in artifacts:
        local_path = project_dir / artifact["local_path"]
        if artifact["local_path"] == MANIFEST_NAME:
            rows.append(
                {
                    **artifact,
                    "bytes": 0,
                    "sha256": "self-referential",
                }
            )
            continue
        if not local_path.exists():
            raise SystemExit(f"Missing expected artifact: {local_path}")
        rows.append(
            {
                **artifact,
                "bytes": local_path.stat().st_size,
                "sha256": file_digest(local_path),
            }
        )
    manifest = {
        "generated_at": generated_at,
        "drive_folder_url": config.get("drive_folder_url", ""),
        "github_repo_url": config.get("github_repo_url", ""),
        "artifacts": rows,
    }
    (project_dir / MANIFEST_NAME).write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")


def build_payload(project_dir: Path, secret: str, artifacts: list[dict[str, str]]) -> dict[str, object]:
    files = []
    for artifact in artifacts:
        local_path = project_dir / artifact["local_path"]
        if not local_path.exists():
            raise SystemExit(f"Missing expected artifact: {local_path}")
        drive_name = artifact["drive_name"]
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
    parser = argparse.ArgumentParser(description="Publish the current LSQ workspace files to Google Drive.")
    parser.add_argument("--project-dir", type=Path, default=Path.cwd())
    parser.add_argument("--config", default=DEFAULT_CONFIG)
    parser.add_argument("--web-app-url", default=os.environ.get("APPS_SCRIPT_WEB_APP_URL", ""))
    parser.add_argument("--secret", default=os.environ.get("APPS_SCRIPT_UPLOAD_SECRET", ""))
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    project_dir = args.project_dir.resolve()
    config = load_config(project_dir / args.config)
    artifacts = artifact_paths(project_dir, config)

    write_index(project_dir, config, artifacts)
    write_manifest(project_dir, config, artifacts)

    if args.dry_run:
        for artifact in artifacts:
            print(f"DRY RUN: {project_dir / artifact['local_path']} -> {artifact['drive_name']}")
        return

    if not args.web_app_url:
        raise SystemExit("Missing Apps Script web app URL. Set APPS_SCRIPT_WEB_APP_URL.")
    if not args.secret:
        raise SystemExit("Missing upload secret. Set APPS_SCRIPT_UPLOAD_SECRET.")

    body = json.dumps(build_payload(project_dir, args.secret, artifacts)).encode("utf-8")
    request = urllib.request.Request(
        args.web_app_url,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=180) as response:
        result = json.loads(response.read().decode("utf-8"))
    if not result.get("ok"):
        raise SystemExit(f"Apps Script upload failed: {result}")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
