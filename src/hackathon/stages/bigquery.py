"""BigQuery source and sink. Auth uses Application Default Credentials
(`gcloud auth application-default login`); the project comes from GCP_PROJECT_ID."""

from __future__ import annotations

import os
from typing import TYPE_CHECKING

import pandas as pd

if TYPE_CHECKING:
    from google.cloud import bigquery


def _bq():
    try:
        from google.cloud import bigquery
    except ImportError as exc:
        raise RuntimeError(
            "BigQuery support is optional. Install it with `pip install -e '.[gcp]'`."
        ) from exc
    return bigquery


def get_client(project: str | None = None) -> bigquery.Client:
    bigquery = _bq()
    project = project or os.getenv("GCP_PROJECT_ID")
    if not project:
        raise ValueError("No GCP project: set GCP_PROJECT_ID in .env")
    return bigquery.Client(project=project)


def ingest_bq(
    query: str, max_bytes_billed: int | None = None, client: bigquery.Client | None = None
) -> pd.DataFrame:
    """Run a SQL query and return the result as a DataFrame."""
    bigquery = _bq()
    client = client or get_client()
    job_config = bigquery.QueryJobConfig(maximum_bytes_billed=max_bytes_billed)
    return client.query(query, job_config=job_config).to_dataframe()


def write_bq(
    df: pd.DataFrame,
    table: str,
    write_disposition: str = "WRITE_TRUNCATE",
    client: bigquery.Client | None = None,
) -> pd.DataFrame:
    """Load a DataFrame into `dataset.table` (or `project.dataset.table`)."""
    bigquery = _bq()
    client = client or get_client()
    job_config = bigquery.LoadJobConfig(write_disposition=write_disposition, autodetect=True)
    client.load_table_from_dataframe(df, table, job_config=job_config).result()
    return df
