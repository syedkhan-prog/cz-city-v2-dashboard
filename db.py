"""Databricks SQL client for SK FF Provider Dashboard."""
from __future__ import annotations

import os

import pandas as pd

DEFAULT_HOSTNAME = "bolt-incentives.cloud.databricks.com"
DEFAULT_HTTP_PATH = "sql/protocolv1/o/2472566184436351/0505-112942-d3yviznw"


def on_databricks() -> bool:
    return bool(os.environ.get("DATABRICKS_RUNTIME_VERSION"))


def _connect():
    from databricks import sql

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
        if on_databricks():
            from pyspark.sql import SparkSession

            self._spark = SparkSession.builder.getOrCreate()
            self.conn = None
        else:
            self._spark = None
            self.conn = _connect()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

    def query(self, q: str) -> pd.DataFrame:
        if self._spark is not None:
            return self._spark.sql(q).toPandas()
        with self.conn.cursor() as cur:
            cur.execute(q)
            cols = [d[0] for d in cur.description]
            return pd.DataFrame(cur.fetchall(), columns=cols)

    def close(self) -> None:
        if self.conn is None:
            return
        try:
            self.conn.close()
        except Exception:
            pass
