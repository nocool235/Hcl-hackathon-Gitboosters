"""Generic cleaning. Replace/extend with problem-specific logic."""

from __future__ import annotations

import pandas as pd


def transform(df: pd.DataFrame, drop_duplicates: bool = True) -> pd.DataFrame:
    df = df.copy()
    df.columns = [str(c).strip().lower().replace(" ", "_") for c in df.columns]
    if drop_duplicates:
        df = df.drop_duplicates().reset_index(drop=True)
    return df
