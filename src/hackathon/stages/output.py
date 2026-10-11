"""Write results to disk (CSV by default)."""

from __future__ import annotations

from pathlib import Path

import pandas as pd


def write_output(df: pd.DataFrame, path: str | Path) -> pd.DataFrame:
    if path is None:
        raise ValueError("An output path is required")
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    suffix = path.suffix.lower()
    if suffix in {".csv", ""}:
        df.to_csv(path, index=False)
    elif suffix == ".tsv":
        df.to_csv(path, sep="\t", index=False)
    elif suffix == ".json":
        df.to_json(path, orient="records", date_format="iso")
    elif suffix == ".parquet":
        df.to_parquet(path, index=False)
    elif suffix == ".xlsx":
        df.to_excel(path, index=False)
    else:
        raise ValueError("Unsupported output type; use .csv, .tsv, .json, .parquet, or .xlsx")
    return df
