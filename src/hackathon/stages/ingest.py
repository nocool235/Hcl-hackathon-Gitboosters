"""Read a tabular file into a DataFrame. Format is chosen by file extension."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

READERS = {
    ".csv": pd.read_csv,
    ".tsv": lambda p: pd.read_csv(p, sep="\t"),
    ".json": pd.read_json,
    ".parquet": pd.read_parquet,
    ".xlsx": pd.read_excel,
}


def ingest(path: str | Path) -> pd.DataFrame:
    path = Path(path)
    reader = READERS.get(path.suffix.lower())
    if reader is None:
        raise ValueError(f"Unsupported file type: {path.suffix} (supported: {sorted(READERS)})")
    return reader(path)
