"""Procurement / Supplier tools — typed functions over the suppliers / purchase_orders tables."""

from __future__ import annotations

from typing import Any

from agent_harness.db.schema import get_connection


def _rows(sql: str, *params) -> list[dict[str, Any]]:
    with get_connection() as conn:
        rows = conn.execute(sql, params).fetchall()
        return [dict(r) for r in rows]


def _row(sql: str, *params) -> dict[str, Any] | None:
    with get_connection() as conn:
        row = conn.execute(sql, params).fetchone()
        return dict(row) if row else None


def list_suppliers() -> list[dict[str, Any]]:
    """Return all suppliers with country, sourcing category, and scorecard rating."""
    return _rows(
        "SELECT id, name, country, category, rating, created_at FROM suppliers ORDER BY name"
    )


def get_supplier(supplier_id: int) -> dict[str, Any] | None:
    """Get full details for one supplier.

    Args:
        supplier_id: The supplier's integer ID.
    """
    return _row(
        "SELECT id, name, country, category, rating, created_at FROM suppliers WHERE id = ?",
        supplier_id,
    )


def search_suppliers(
    country: str = "", category: str = "", min_rating: float = 0.0, limit: int = 20
) -> list[dict[str, Any]]:
    """Search suppliers by country, sourcing category, or minimum scorecard rating.

    Args:
        country: Two-letter ISO country code filter. Empty = no filter.
        category: Exact sourcing category filter
            ('raw_materials','logistics','software','facilities','professional_services').
        min_rating: Minimum 1-5 scorecard rating. 0 means no filter.
        limit: Maximum results (default 20).
    """
    conditions = ["1=1"]
    params: list[Any] = []
    if country:
        conditions.append("country = ?")
        params.append(country)
    if category:
        conditions.append("category = ?")
        params.append(category)
    if min_rating > 0:
        conditions.append("rating >= ?")
        params.append(min_rating)
    params.append(limit)
    where = " AND ".join(conditions)
    return _rows(
        f"SELECT id, name, country, category, rating FROM suppliers WHERE {where}"
        f" ORDER BY rating DESC LIMIT ?",
        *params,
    )


def get_purchase_order(po_id: int) -> dict[str, Any] | None:
    """Get full details for one purchase order, including the supplier name.

    Args:
        po_id: The purchase order's integer ID.
    """
    return _row(
        """
        SELECT po.id, s.name AS supplier_name, po.status, po.total_amount,
               po.ordered_at, po.expected_at, po.received_at
        FROM purchase_orders po
        JOIN suppliers s ON s.id = po.supplier_id
        WHERE po.id = ?
        """,
        po_id,
    )


def get_supplier_purchase_history(supplier_id: int, limit: int = 20) -> list[dict[str, Any]]:
    """Return a supplier's purchase order history, most recent first.

    Args:
        supplier_id: The supplier's integer ID.
        limit: Maximum purchase orders to return (default 20).
    """
    return _rows(
        """
        SELECT id, status, total_amount, ordered_at, expected_at, received_at
        FROM purchase_orders
        WHERE supplier_id = ?
        ORDER BY ordered_at DESC
        LIMIT ?
        """,
        supplier_id,
        limit,
    )


def get_supplier_performance(supplier_id: int) -> dict[str, Any] | None:
    """Return a supplier's PO volume, total spend, and on-time delivery rate.

    Args:
        supplier_id: The supplier's integer ID.
    """
    return _row(
        """
        SELECT s.id, s.name, s.rating,
               COUNT(po.id) AS total_purchase_orders,
               ROUND(SUM(po.total_amount), 2) AS total_spend_usd,
               SUM(CASE WHEN po.status = 'received' THEN 1 ELSE 0 END) AS received_count,
               SUM(CASE WHEN po.status = 'received' AND po.received_at <= po.expected_at
                        THEN 1 ELSE 0 END) AS on_time_count
        FROM suppliers s
        LEFT JOIN purchase_orders po ON po.supplier_id = s.id
        WHERE s.id = ?
        GROUP BY s.id
        """,
        supplier_id,
    )


def get_late_delivery_report(days: int = 180) -> list[dict[str, Any]]:
    """Return purchase orders received late (after expected_at) in the last N days, by supplier.

    Args:
        days: Look-back window in days, based on ordered_at (default 180).
    """
    return _rows(
        """
        WITH latest AS (SELECT MAX(ordered_at) AS max_ordered_at FROM purchase_orders)
        SELECT po.id AS po_id, s.name AS supplier_name, po.expected_at, po.received_at,
               CAST(JULIANDAY(po.received_at) - JULIANDAY(po.expected_at) AS INTEGER)
                 AS days_late
        FROM purchase_orders po
        JOIN suppliers s ON s.id = po.supplier_id
        CROSS JOIN latest
        WHERE po.status = 'received'
          AND po.received_at > po.expected_at
          AND po.ordered_at >= datetime(latest.max_ordered_at, ? || ' days')
        ORDER BY days_late DESC
        """,
        f"-{days}",
    )


def get_procurement_spend_summary(start_date: str, end_date: str) -> dict[str, Any]:
    """Aggregate procurement spend metrics between two ISO-8601 dates (inclusive), based on
    ordered_at.

    Args:
        start_date: Start of the period, e.g. '2024-01-01'.
        end_date: End of the period, e.g. '2024-03-31'.
    """
    return _row(
        """
        SELECT COUNT(*) AS total_purchase_orders,
               ROUND(SUM(total_amount), 2) AS total_spend_usd,
               ROUND(AVG(total_amount), 2) AS avg_po_value,
               COUNT(DISTINCT supplier_id) AS distinct_suppliers
        FROM purchase_orders
        WHERE status != 'cancelled'
          AND ordered_at BETWEEN ? AND ?
        """,
        start_date,
        end_date + "T23:59:59",
    )


def get_supplier_risk_score(supplier_id: int) -> dict[str, Any] | None:
    """Compute a simple supplier risk score from scorecard rating and on-time delivery rate.

    Formula: risk_score = round((5 - rating) * 10 + (100 - on_time_rate_pct) * 0.5, 2).
    Higher scores mean higher risk.

    Args:
        supplier_id: The supplier's integer ID.
    """
    perf = get_supplier_performance(supplier_id)
    if perf is None:
        return None
    received = perf["received_count"] or 0
    on_time_rate_pct = round(100 * (perf["on_time_count"] or 0) / received, 2) if received else None
    if on_time_rate_pct is None:
        return {**perf, "on_time_rate_pct": None, "risk_score": None}
    risk_score = round((5 - perf["rating"]) * 10 + (100 - on_time_rate_pct) * 0.5, 2)
    return {**perf, "on_time_rate_pct": on_time_rate_pct, "risk_score": risk_score}
