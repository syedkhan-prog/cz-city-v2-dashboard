"""Boltable entrypoint — uvicorn on 0.0.0.0:$PORT."""
from __future__ import annotations

import os

import uvicorn

if __name__ == "__main__":
    port = int(os.environ.get("PORT", "8080"))
    print(f"CZ City V2 dashboard listening on 0.0.0.0:{port}", flush=True)
    uvicorn.run("app:app", host="0.0.0.0", port=port)
