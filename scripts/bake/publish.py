"""Commit baked files and push origin main using GIT_ASKPASS."""

from __future__ import annotations

import subprocess
from datetime import datetime, timezone
from pathlib import Path

from secrets_util import git_env, github_token


def publish(root: Path, add_paths: list[str], message: str) -> None:
    root = Path(root)
    token = github_token()
    subprocess.run(
        ["git", "-C", str(root), "config", "user.name", "dashboard-bake"],
        check=True,
    )
    subprocess.run(
        [
            "git",
            "-C",
            str(root),
            "config",
            "user.email",
            "41898282+github-actions[bot]@users.noreply.github.com",
        ],
        check=True,
    )
    subprocess.run(["git", "-C", str(root), "add", "--", *add_paths], check=True)
    diff = subprocess.run(["git", "-C", str(root), "diff", "--cached", "--quiet"])
    if diff.returncode == 0:
        print("No snapshot changes to push", flush=True)
        return
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    subprocess.run(
        ["git", "-C", str(root), "commit", "-m", f"{message} ({stamp})"],
        check=True,
    )
    subprocess.run(
        [
            "git",
            "-C",
            str(root),
            "-c",
            "credential.helper=",
            "push",
            "origin",
            "HEAD:main",
        ],
        check=True,
        env=git_env(token),
    )
    print(f"Pushed snapshot to origin/main: {message}", flush=True)
