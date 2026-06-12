from __future__ import annotations

import argparse
import os
import shutil
import stat
import subprocess
import tempfile
from pathlib import Path


def run_git(args: list[str], cwd: Path, env: dict[str, str] | None = None) -> None:
    result = subprocess.run(
        ["git", *args],
        cwd=cwd,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        timeout=120,
    )
    if result.returncode != 0:
        output = result.stdout.replace(os.environ.get("OVERLEAF_GIT_TOKEN", ""), "***")
        raise SystemExit(f"git {' '.join(args)} failed:\n{output}")


def make_askpass(path: Path) -> Path:
    askpass = path / "overleaf_askpass.sh"
    askpass.write_text(
        "#!/bin/sh\n"
        "case \"$1\" in\n"
        "  *Username*) echo git ;;\n"
        "  *Password*) echo \"$OVERLEAF_GIT_TOKEN\" ;;\n"
        "  *) echo \"$OVERLEAF_GIT_TOKEN\" ;;\n"
        "esac\n",
        encoding="utf-8",
    )
    askpass.chmod(askpass.stat().st_mode | stat.S_IXUSR)
    return askpass


def push(workspace_dir: Path, remote_url: str, token: str) -> None:
    if not workspace_dir.exists():
        raise SystemExit(f"Missing LaTeX workspace folder: {workspace_dir}")
    if not remote_url:
        raise SystemExit("Missing OVERLEAF_GIT_URL.")
    if not token:
        raise SystemExit("Missing OVERLEAF_GIT_TOKEN.")

    with tempfile.TemporaryDirectory() as tmp:
        repo_dir = Path(tmp) / "overleaf_repo"
        shutil.copytree(workspace_dir, repo_dir)
        askpass = make_askpass(Path(tmp))
        env = os.environ.copy()
        env["GIT_ASKPASS"] = str(askpass)
        env["GIT_TERMINAL_PROMPT"] = "0"
        env["OVERLEAF_GIT_TOKEN"] = token

        run_git(["init", "-b", "master"], repo_dir, env)
        run_git(["config", "user.name", "project-workspace-bot"], repo_dir, env)
        run_git(["config", "user.email", "project-workspace-bot@users.noreply.github.com"], repo_dir, env)
        run_git(["add", "."], repo_dir, env)
        run_git(["commit", "-m", "Update live LaTeX workspace"], repo_dir, env)
        run_git(["remote", "add", "overleaf", remote_url], repo_dir, env)
        run_git(["push", "--force", "overleaf", "master"], repo_dir, env)


def main() -> None:
    parser = argparse.ArgumentParser(description="Push the generated LaTeX workspace to an Overleaf Git project.")
    parser.add_argument("--workspace-dir", type=Path, default=Path("_latex_workspace"))
    parser.add_argument("--remote-url", default=os.environ.get("OVERLEAF_GIT_URL", ""))
    parser.add_argument("--token", default=os.environ.get("OVERLEAF_GIT_TOKEN", ""))
    args = parser.parse_args()
    push(args.workspace_dir.resolve(), args.remote_url, args.token)
    print("Pushed live LaTeX workspace to Overleaf.")


if __name__ == "__main__":
    main()
