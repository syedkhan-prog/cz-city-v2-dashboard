"""Embed data.json into the HTML template -> deployable dashboard builds."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent


def _render(tpl: str, data: dict, *, boltable: bool) -> str:
    payload = json.dumps(data, ensure_ascii=False).replace("</", "<\\/")
    config = json.dumps({"boltable": boltable})
    return tpl.replace("__DATA__", payload).replace("__CONFIG__", config)


def build(*, write_local: bool = True) -> dict[str, Path]:
    data = json.loads((HERE / "data.json").read_text(encoding="utf-8"))
    tpl = (HERE / "web" / "index.html").read_text(encoding="utf-8")
    out: dict[str, Path] = {}

    docs = HERE / "docs" / "index.html"
    docs.parent.mkdir(exist_ok=True)
    docs.write_text(_render(tpl, data, boltable=False), encoding="utf-8")
    out["docs"] = docs

    boltable = HERE / "boltable" / "index.html"
    boltable.parent.mkdir(exist_ok=True)
    boltable.write_text(_render(tpl, data, boltable=True), encoding="utf-8")
    out["boltable"] = boltable

    if write_local:
        local = HERE.parent / "CZ_City_V2_Setup_Dashboard.html"
        local.write_text(_render(tpl, data, boltable=False), encoding="utf-8")
        out["local"] = local

    return out


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--no-local", action="store_true", help="Skip ~/Downloads standalone HTML")
    args = parser.parse_args()
    paths = build(write_local=not args.no_local)
    for name, path in paths.items():
        kb = path.stat().st_size / 1024
        print(f"Wrote {path} ({kb:.0f} KB)")
