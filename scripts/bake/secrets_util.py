"""Load GitHub secrets on Databricks. Do not put the token on a git argv."""

from __future__ import annotations

import os
import stat
import tempfile
from pathlib import Path


def on_databricks() -> bool:
    return bool(os.environ.get("DATABRICKS_RUNTIME_VERSION"))


def _dbutils():
    try:
        from pyspark.dbutils import DBUtils
        from pyspark.sql import SparkSession

        return DBUtils(SparkSession.builder.getOrCreate())
    except Exception:
        try:
            import IPython

            return IPython.get_ipython().user_ns["dbutils"]
        except Exception as exc:
            raise RuntimeError("dbutils is not available") from exc


def github_token() -> str:
    token = os.environ.get("GITHUB_TOKEN", "").strip()
    if token:
        return token
    if on_databricks():
        scope = os.environ.get("GITHUB_SECRET_SCOPE", "campaign-tracker")
        key = os.environ.get("GITHUB_SECRET_KEY", "github_pat")
        token = _dbutils().secrets.get(scope=scope, key=key).strip()
        if token:
            return token
    raise SystemExit(
        "GitHub token missing. Set GITHUB_TOKEN or Databricks secret "
        "campaign-tracker/github_pat with contents:write on the boltable repo."
    )


def git_env(token: str) -> dict[str, str]:
    fd, name = tempfile.mkstemp(prefix="dash-git-askpass-", suffix=".sh")
    os.close(fd)
    script = Path(name)
    script.write_text(
        "#!/bin/sh\n"
        'if echo "$1" | grep -qi username; then\n'
        "  echo x-access-token\n"
        "else\n"
        '  echo "$GIT_PASSWORD"\n'
        "fi\n"
    )
    script.chmod(stat.S_IRUSR | stat.S_IWUSR | stat.S_IXUSR)
    env = os.environ.copy()
    env["GIT_ASKPASS"] = str(script)
    env["GIT_TERMINAL_PROMPT"] = "0"
    env["GIT_PASSWORD"] = token
    env["GCM_INTERACTIVE"] = "never"
    return env
