"""Generic cleaning. Replace/extend with problem-specific logic."""

from __future__ import annotations

import re

import pandas as pd


def transform(df: pd.DataFrame, drop_duplicates: bool = True) -> pd.DataFrame:
    df = df.copy()
    columns = []
    for column in df.columns:
        name = re.sub(r"[^a-z0-9]+", "_", str(column).strip().lower()).strip("_")
        columns.append(name or "unnamed")
    if len(columns) != len(set(columns)):
        duplicates = sorted({c for c in columns if columns.count(c) > 1})
        raise ValueError(f"Column normalization creates duplicate names: {duplicates}")
    df.columns = columns
    if drop_duplicates:
        df = df.drop_duplicates().reset_index(drop=True)
    return df
