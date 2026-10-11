"""All SQLite access lives here, so another database could replace it later."""

from __future__ import annotations

import sqlite3
from decimal import Decimal
from pathlib import Path

AUDIT_TABLES = ("pipeline_runs",)
sqlite3.register_adapter(Decimal, str)


def connect(path: str | Path) -> sqlite3.Connection:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def _sql_type(values: list) -> str:
    present = [v for v in values if v is not None]
    # SQLite has no fixed-precision decimal type. Store Decimal values as text so their exact
    # cents survive the local database boundary; the BigQuery loader maps them to NUMERIC.
    if present and any(isinstance(v, Decimal) for v in present):
        return "TEXT"
    if present and all(isinstance(v, int) for v in present):
        return "INTEGER"
    if present and all(isinstance(v, (int, float, Decimal)) for v in present):
        return "NUMERIC"
    return "TEXT"


def write_table(
    conn: sqlite3.Connection,
    name: str,
    columns: list[str],
    rows: list[dict],
    primary_key: str | None = None,
    foreign_keys: list[tuple[str, str, str]] | None = None,
) -> None:
    """Drop and recreate a table, so a rerun never leaves duplicates behind."""
    types = {c: _sql_type([r.get(c) for r in rows]) for c in columns}
    definitions = [f'"{c}" {types[c]}' for c in columns]
    if primary_key:
        definitions.append(f'PRIMARY KEY ("{primary_key}")')
    for column, parent_table, parent_column in foreign_keys or []:
        definitions.append(
            f'FOREIGN KEY ("{column}") REFERENCES "{parent_table}" ("{parent_column}")'
        )
    ddl = ", ".join(definitions)
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
    # This is a controlled rebuild, so temporarily disable enforcement while removing the old
    # graph. It also handles dimension-to-dimension dependencies such as product -> supplier.
    conn.execute("PRAGMA foreign_keys = OFF")
    try:
        for name in table_names(conn):
            if name not in AUDIT_TABLES:
                conn.execute(f'DROP TABLE "{name}"')
        conn.commit()
    finally:
        conn.execute("PRAGMA foreign_keys = ON")
