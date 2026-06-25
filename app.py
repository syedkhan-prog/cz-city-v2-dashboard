"""CZ City V2 Setup Dashboard — Boltable + local static server."""
from __future__ import annotations

import os
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import HTMLResponse, PlainTextResponse

HERE = Path(__file__).resolve().parent


def is_boltable() -> bool:
    if os.environ.get("LOCAL_DEV") == "1":
        return False
    if os.environ.get("BOLTABLE") == "1" or os.environ.get("BPE_BOLTABLE") == "1":
        return True
    # Boltable runs on Kubernetes — BPE_BOLTABLE is build-time only, not injected at runtime.
    return bool(os.environ.get("KUBERNETES_SERVICE_HOST"))


HTML_PATH = HERE / ("boltable" if is_boltable() else "docs") / "index.html"

app = FastAPI(title="CZ City V2 Setup Dashboard")


@app.get("/health", response_class=PlainTextResponse)
def health() -> str:
    return "ok"


@app.get("/", response_class=HTMLResponse)
def index() -> HTMLResponse:
    if not HTML_PATH.exists():
        return HTMLResponse(
            "<h1>Dashboard not built yet</h1><p>Run <code>python fetch.py && python build.py</code>.</p>",
            status_code=503,
        )
    return HTMLResponse(
        HTML_PATH.read_text(encoding="utf-8"),
        headers={"Cache-Control": "no-store"},
    )


if __name__ == "__main__":
    import uvicorn

    port = int(os.environ.get("PORT", "8082"))
    print(f"\n→ Dashboard at http://localhost:{port}\n", flush=True)
    uvicorn.run(app, host="0.0.0.0", port=port)
