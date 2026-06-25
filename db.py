"""Databricks SQL client for SK FF Provider Dashboard."""
from __future__ import annotations

import os

import pandas as pd
from databricks import sql

DEFAULT_HOSTNAME = "bolt-incentives.cloud.databricks.com"
DEFAULT_HTTP_PATH = "sql/protocolv1/o/2472566184436351/0221-081903-9ag4bh69"


def _connect():
    hostname = os.environ.get("DATABRICKS_SERVER_HOSTNAME", DEFAULT_HOSTNAME)
    http_path = os.environ.get("DATABRICKS_HTTP_PATH", DEFAULT_HTTP_PATH)
    token = os.environ.get("DATABRICKS_TOKEN")
    if token:
        return sql.connect(
            server_hostname=hostname,
            http_path=http_path,
            access_token=token,
        )
    return sql.connect(
        server_hostname=hostname,
        http_path=http_path,
        auth_type="databricks-oauth",
    )


class DBX:
    def __init__(self):
        self.conn = _connect()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

    def query(self, q: str) -> pd.DataFrame:
        with self.conn.cursor() as cur:
            cur.execute(q)
            cols = [d[0] for d in cur.description]
            return pd.DataFrame(cur.fetchall(), columns=cols)

    def close(self) -> None:
        try:
            self.conn.close()
        except Exception:
            pass
