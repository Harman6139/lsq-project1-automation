from __future__ import annotations

import argparse
import zipfile
from datetime import datetime
from pathlib import Path


ZIP_NAME = "Boyle_LSQ_Workspace_Overleaf_Latest.zip"

PROJECT1_FILES = [
    "Project_1_May2026_Update.tex",
    "Project_1_May2026_Update.pdf",
    "Project_1_May2026_Update.xlsx",
    "manifest.json",
    "data/lsq_returns.csv",
    "data/sp500tr_returns.csv",
    "data/nvda_returns.csv",
    "data/market_return_verification.csv",
    "tables/updated_table_2.csv",
    "tables/updated_table_2.tex",
    "tables/updated_table_4.csv",
    "tables/updated_table_4.tex",
    "scripts/update_project1_monthly.py",
]

SKIP_NAMES = {
    "apps_script_upload_secret.txt",
    "Code_for_paste.gs",
    "LSQ-Oct21-live.pdf",
}
SKIP_SUFFIXES = {".aux", ".fdb_latexmk", ".fls", ".log", ".out", ".pyc"}


def should_skip(path: Path) -> bool:
    return (
        path.name in SKIP_NAMES
        or path.suffix.lower() in SKIP_SUFFIXES
        or "__pycache__" in path.parts
        or ".git" in path.parts
    )


def add_file(zf: zipfile.ZipFile, source: Path, arcname: str) -> None:
    if not source.exists():
        raise SystemExit(f"Missing expected workspace file: {source}")
    if should_skip(source):
        return
    zf.write(source, arcname)


def add_tree(zf: zipfile.ZipFile, source_dir: Path, arc_prefix: str) -> None:
    if not source_dir.exists():
        raise SystemExit(f"Missing expected workspace folder: {source_dir}")
    for path in sorted(source_dir.rglob("*")):
        if path.is_dir() or should_skip(path):
            continue
        arcname = f"{arc_prefix}/{path.relative_to(source_dir).as_posix()}"
        zf.write(path, arcname)


def build(project_dir: Path) -> Path:
    project_dir = project_dir.resolve()
    zip_path = project_dir / ZIP_NAME
    if zip_path.exists():
        zip_path.unlink()

    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        readme = (
            "Boyle LSQ Workspace\n"
            f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
            "Project_1_May2026_Update contains the current monthly Project 1 update.\n"
            "Assignment_2 contains the leveraged S&P 500 analysis.\n\n"
            "For the viewer-ready version, open the PDF files in Google Drive.\n"
            "For LaTeX source, open the .tex file inside the relevant project folder.\n"
        )
        zf.writestr("README_WORKSPACE.txt", readme)

        for relative_path in PROJECT1_FILES:
            add_file(
                zf,
                project_dir / relative_path,
                f"Project_1_May2026_Update/{Path(relative_path).as_posix()}",
            )

        add_tree(zf, project_dir / "workspace" / "assignment_2", "Assignment_2")

    return zip_path


def main() -> None:
    parser = argparse.ArgumentParser(description="Build the current professor-facing LaTeX workspace bundle.")
    parser.add_argument("--project-dir", type=Path, default=Path.cwd())
    args = parser.parse_args()
    print(build(args.project_dir))


if __name__ == "__main__":
    main()
