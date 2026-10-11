"""All SQLite access lives here, so another database could replace it later."""

from __future__ import annotations

import sqlite3
from pathlib import Path

AUDIT_TABLES = ("pipeline_runs",)


def connect(path: str | Path) -> sqlite3.Connection:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    return conn


def _sql_type(values: list) -> str:
    present = [v for v in values if v is not None]
    if present and all(isinstance(v, int) for v in present):
        return "INTEGER"
    if present and all(isinstance(v, (int, float)) for v in present):
        return "REAL"
    return "TEXT"


def write_table(conn: sqlite3.Connection, name: str, columns: list[str], rows: list[dict]) -> None:
    """Drop and recreate a table, so a rerun never leaves duplicates behind."""
    types = {c: _sql_type([r.get(c) for r in rows]) for c in columns}
    ddl = ", ".join(f'"{c}" {types[c]}' for c in columns)
    conn.execute(f'DROP TABLE IF EXISTS "{name}"')
    conn.execute(f'CREATE TABLE "{name}" ({ddl})')
    placeholders = ", ".join("?" for _ in columns)
    conn.executemany(
        f'INSERT INTO "{name}" VALUES ({placeholders})',
        [tuple(r.get(c) for c in columns) for r in rows],
    )
    conn.commit()


def read_rows(conn: sqlite3.Connection, table: str) -> list[dict]:
    return [dict(r) for r in conn.execute(f'SELECT * FROM "{table}"')]


def table_names(conn: sqlite3.Connection) -> list[str]:
    cur = conn.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
    return [r["name"] for r in cur]


def reset_database(conn: sqlite3.Connection) -> None:
    """Drop every table except the audit log, so each run starts from a clean slate."""
    for name in table_names(conn):
        if name not in AUDIT_TABLES:
            conn.execute(f'DROP TABLE "{name}"')
    conn.commit()
