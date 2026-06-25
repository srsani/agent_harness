"""Raw SQL tools — the escape hatch a ReAct agent or power user would reach for.

All tools are read-only (SELECT only). Three tools are provided:

  list_tables()         — all tables with semantic names, descriptions, and column signatures
  describe_table(name)  — full column definitions plus semantic descriptions for one table
  execute_sql(query)    — run any SELECT and get columns + rows back
  get_schema_context()  — full semantic layer: tables, columns, relationships, metric patterns
"""

from __future__ import annotations

import sqlite3
from typing import Any

from agent_harness.db.schema import (
    BUSINESS_METRICS,
    RELATIONSHIPS,
    SCHEMA_METADATA,
    get_connection,
)


class SQLError(Exception):
    pass


_BLOCKED = ("insert", "update", "delete", "drop", "alter", "create", "attach", "pragma")


def list_tables() -> list[dict[str, Any]]:
    """Return all tables with their semantic name, description, and column signatures.

    Each entry includes:
      table          — physical SQL table name
      semantic_name  — business-domain name for the table
      description    — what the table represents and key facts about the data
      columns        — comma-separated 'column_name TYPE' pairs
    """
    with get_connection() as conn:
        tables = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        ).fetchall()
        result = []
        for (tname,) in tables:
            cols = conn.execute(f"PRAGMA table_info({tname})").fetchall()  # noqa: S608
            col_summary = ", ".join(f"{c['name']} {c['type']}" for c in cols)
            meta = SCHEMA_METADATA.get(tname, {})
            result.append({
                "table": tname,
                "semantic_name": meta.get("semantic_name", tname),
                "description": meta.get("description", ""),
                "columns": col_summary,
            })
        return result


def describe_table(table_name: str) -> list[dict[str, Any]]:
    """Return full column definitions plus semantic descriptions for a table.

    Each column entry includes:
      name          — physical column name
      type          — SQLite affinity (INTEGER, REAL, TEXT, …)
      notnull       — 1 if NOT NULL, else 0
      pk            — 1 if part of PRIMARY KEY, else 0
      dflt_value    — DEFAULT expression if any
      description   — plain-English meaning of the column in this domain
      fk_to         — 'table.column' if this column is a foreign key, else null

    Args:
        table_name: Exact SQL table name (e.g. 'order_items').
    """
    with get_connection() as conn:
        rows = conn.execute(f"PRAGMA table_info({table_name})").fetchall()  # noqa: S608
        if not rows:
            raise SQLError(f"Table '{table_name}' not found.")
        fk_rows = conn.execute(
            f"PRAGMA foreign_key_list({table_name})"  # noqa: S608
        ).fetchall()

    fk_map = {r["from"]: f"{r['table']}.{r['to']}" for r in fk_rows}
    col_meta = SCHEMA_METADATA.get(table_name, {}).get("columns", {})

    return [
        {
            "name": r["name"],
            "type": r["type"],
            "notnull": r["notnull"],
            "pk": r["pk"],
            "dflt_value": r["dflt_value"],
            "description": col_meta.get(r["name"], ""),
            "fk_to": fk_map.get(r["name"]),
        }
        for r in rows
    ]


def get_schema_context() -> dict[str, Any]:
    """Return the full semantic layer context for the enterprise Decision Intelligence database.

    Use this tool first when building complex queries or when you need to understand
    the data model before choosing between semantic tools and raw SQL.

    Returns a dict with four keys:

      tables        — for each table: semantic name, description, columns with domain meanings
      relationships — all foreign-key links between tables
      business_metrics — canonical SQL patterns for common enterprise KPIs
      query_tips    — join patterns and filtering conventions to follow

    Typical usage:
      1. Call get_schema_context() once to understand the model.
      2. Use the semantic tools (search_products, get_customer, etc.) for common lookups.
      3. Fall back to execute_sql() for anything the semantic tools don't cover.
    """
    tables_out = {}
    for tname, meta in SCHEMA_METADATA.items():
        tables_out[tname] = {
            "semantic_name": meta["semantic_name"],
            "description": meta["description"],
            "columns": meta["columns"],
        }

    return {
        "tables": tables_out,
        "relationships": RELATIONSHIPS,
        "business_metrics": BUSINESS_METRICS,
        "query_tips": [
            "Always filter orders with status != 'cancelled' for revenue metrics.",
            "Use status = 'delivered' for metrics about actively-used subscriptions.",
            "Revenue at line-item level: order_items.seats * order_items.unit_price.",
            "Revenue at order level: orders.total_amount (pre-computed).",
            "Module adoption: products.active_deployments (current snapshot).",
            "Trend analysis: join orders on created_at with date functions.",
            (
                "Tier breakdown: customers.tier IN ('standard','silver','gold') — "
                "standard=analyst, silver=manager, gold=director/VP/C-suite."
            ),
            "User lifetime value: SUM(orders.total_amount) WHERE status != 'cancelled', per user.",
            (
                "Cross-function analysis: join products → categories; "
                "categories.name is the business function label."
            ),
        ],
    }


def execute_sql(query: str, limit: int = 100) -> dict[str, Any]:
    """Execute a read-only SELECT statement and return columns + rows.

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
