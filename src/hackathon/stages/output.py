"""Write results to disk (CSV by default)."""

from __future__ import annotations

from pathlib import Path

import pandas as pd


def write_output(df: pd.DataFrame, path: str | Path) -> pd.DataFrame:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path, index=False)
    return df
