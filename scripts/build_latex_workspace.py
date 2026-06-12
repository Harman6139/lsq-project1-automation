from __future__ import annotations

import argparse
import shutil
from datetime import datetime, timezone
from pathlib import Path


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

ASSIGNMENT2_FILES = [
    "Assignment_2_Leveraged_SP500.tex",
    "Assignment_2_Leveraged_SP500.pdf",
    "assignment2_manifest.json",
    "data/sp500tr_monthly_returns_2017_01_to_2026_05.csv",
    "scripts/compute_assignment2_leveraged_sp500.py",
]


def copy_required(source: Path, target: Path) -> None:
    if not source.exists():
        raise SystemExit(f"Missing expected LaTeX workspace file: {source}")
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, target)


def write_main_tex(out_dir: Path) -> None:
    content = r"""\documentclass[11pt]{article}
\usepackage[margin=1in]{geometry}
\usepackage{hyperref}
\IfFileExists{pdfpages.sty}{%
  \usepackage{pdfpages}
  \newcommand{\workspaceincludepdf}[1]{\includepdf[pages=-]{##1}}
}{%
  \newcommand{\workspaceincludepdf}[1]{\texttt{\detokenize{##1}}}
}
\setlength{\parindent}{0pt}

\begin{document}

\begin{center}
{\Large Boyle LSQ Live Workspace}\\[0.25em]
{\small Generated automatically from the project source repository}
\end{center}

\section*{Current Contents}

This workspace is updated by automation. The source files are organized under \texttt{Project\_1\_Monthly} and \texttt{Assignment\_2}. The compiled PDFs are included below for quick review.

\section*{Project 1 Monthly Update}
\workspaceincludepdf{Project_1_Monthly/Project_1_May2026_Update.pdf}

\section*{Assignment 2}
\workspaceincludepdf{Assignment_2/Assignment_2_Leveraged_SP500.pdf}

\end{document}
"""
    (out_dir / "main.tex").write_text(content, encoding="utf-8")


def write_readme(out_dir: Path) -> None:
    generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    content = (
        "Boyle LSQ Live LaTeX Workspace\n"
        f"Updated: {generated_at}\n\n"
        "This workspace is generated automatically from the project source repository.\n"
        "Open main.tex for a combined viewer-ready document.\n\n"
        "Folders:\n"
        "- Project_1_Monthly: current monthly Project 1 update, tables, data, and script.\n"
        "- Assignment_2: leveraged S&P 500 assignment source, data, and script.\n"
    )
    (out_dir / "README.md").write_text(content, encoding="utf-8")


def build(project_dir: Path, output_dir: Path) -> Path:
    project_dir = project_dir.resolve()
    output_dir = output_dir.resolve()
    if output_dir.exists():
        shutil.rmtree(output_dir)
    output_dir.mkdir(parents=True)

    write_main_tex(output_dir)
    write_readme(output_dir)

    for relative_path in PROJECT1_FILES:
        copy_required(
            project_dir / relative_path,
            output_dir / "Project_1_Monthly" / Path(relative_path).as_posix(),
        )

    assignment2_dir = project_dir / "workspace" / "assignment_2"
    for relative_path in ASSIGNMENT2_FILES:
        copy_required(
            assignment2_dir / relative_path,
            output_dir / "Assignment_2" / Path(relative_path).as_posix(),
        )

    return output_dir


def main() -> None:
    parser = argparse.ArgumentParser(description="Build the live LaTeX workspace folder.")
    parser.add_argument("--project-dir", type=Path, default=Path.cwd())
    parser.add_argument("--output-dir", type=Path, default=Path("_latex_workspace"))
    args = parser.parse_args()
    print(build(args.project_dir, args.output_dir))


if __name__ == "__main__":
    main()
