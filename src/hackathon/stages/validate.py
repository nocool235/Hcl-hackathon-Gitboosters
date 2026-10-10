"""Fail fast on bad input instead of producing wrong results downstream."""

from __future__ import annotations

import pandas as pd


def validate(
    df: pd.DataFrame, required_columns: list[str] | None = None, allow_empty: bool = False
) -> pd.DataFrame:
    if df.empty and not allow_empty:
        raise ValueError("Input data is empty")
    missing = [c for c in (required_columns or []) if c not in df.columns]
    if missing:
        raise ValueError(f"Missing required columns: {missing}")
    return df
