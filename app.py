"""CZ City V2 Setup Dashboard — Boltable + local static server."""
from __future__ import annotations

import os
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import HTMLResponse, PlainTextResponse

HERE = Path(__file__).resolve().parent


def html_path() -> Path:
    # GitHub Pages serves docs/ statically. This app is for Boltable (+ optional local preview).
    if os.environ.get("LOCAL_DEV") == "1":
        return HERE / "docs" / "index.html"
    return HERE / "boltable" / "index.html"


app = FastAPI(title="CZ City V2 Setup Dashboard")


@app.get("/health", response_class=PlainTextResponse)
def health() -> str:
    return "ok"


@app.get("/", response_class=HTMLResponse)
def index() -> HTMLResponse:
    path = html_path()
    if not path.exists():
        return HTMLResponse(
            "<h1>Dashboard not built yet</h1><p>Run <code>python fetch.py && python build.py</code>.</p>",
            status_code=503,
        )
    return HTMLResponse(
        path.read_text(encoding="utf-8"),
        headers={"Cache-Control": "no-store"},
    )


if __name__ == "__main__":
    import uvicorn

    port = int(os.environ.get("PORT", "8082"))
    print(f"\n→ Dashboard at http://localhost:{port}\n", flush=True)
    uvicorn.run(app, host="0.0.0.0", port=port)
