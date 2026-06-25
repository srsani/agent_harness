"""Raw SQL tool — the "escape hatch" a ReAct agent or power user would use.

Restricted to read-only SELECT statements.
"""

from __future__ import annotations

import sqlite3
from typing import Any

from agent_harness.db.schema import get_connection


class SQLError(Exception):
    pass


_BLOCKED = ("insert", "update", "delete", "drop", "alter", "create", "attach", "pragma")


def list_tables() -> list[dict[str, str]]:
    """Return all table names and a brief description of their columns."""
    with get_connection() as conn:
        tables = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        ).fetchall()
        result = []
        for (tname,) in tables:
            cols = conn.execute(f"PRAGMA table_info({tname})").fetchall()  # noqa: S608
            col_summary = ", ".join(f"{c['name']} {c['type']}" for c in cols)
            result.append({"table": tname, "columns": col_summary})
        return result


def describe_table(table_name: str) -> list[dict[str, Any]]:
    """Return column definitions for a table.

    Args:
        table_name: Exact name of the table (e.g. 'orders').
    """
    with get_connection() as conn:
        rows = conn.execute(f"PRAGMA table_info({table_name})").fetchall()  # noqa: S608
        if not rows:
            raise SQLError(f"Table '{table_name}' not found.")
        return [dict(r) for r in rows]


def execute_sql(query: str, limit: int = 100) -> dict[str, Any]:
    """Execute a read-only SQL SELECT and return columns + rows.

    Only SELECT statements are allowed. Results are capped at *limit* rows
    (default 100) to prevent huge outputs.

    Args:
        query: A valid SQLite SELECT statement.
        limit: Row cap applied if no LIMIT clause is present (default 100).
    """
    q = query.strip()
    lower = q.lower()

    if not lower.startswith("select"):
        raise SQLError("Only SELECT statements are allowed.")
    for blocked in _BLOCKED:
        if f" {blocked} " in f" {lower} ":
            raise SQLError(f"Blocked keyword '{blocked}' is not allowed.")

    if "limit" not in lower:
        q = f"{q} LIMIT {limit}"

    try:
        with get_connection() as conn:
            cur = conn.execute(q)
            cols = [d[0] for d in cur.description] if cur.description else []
            rows = [dict(zip(cols, r)) for r in cur.fetchall()]
        return {"columns": cols, "rows": rows, "row_count": len(rows)}
    except sqlite3.Error as exc:
        raise SQLError(str(exc)) from exc
