"""Bake CZ city v2 JSON + HTML and push Boltable main."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(os.environ.get("DASHBOARD_ROOT") or Path(__file__).resolve().parents[2])
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from publish import publish  # noqa: E402


def main() -> None:
    os.chdir(ROOT)
    import fetch
    import build

    print("pulling city v2 data", flush=True)
    data = fetch.pull()
    (ROOT / "data.json").write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    print("building HTML", flush=True)
    build.build(write_local=False)
    publish(
        ROOT,
        ["data.json", "docs/index.html", "boltable/index.html"],
        "chore: Databricks CZ city v2 refresh",
    )


if __name__ == "__main__":
    main()
