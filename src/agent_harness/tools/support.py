"""Support & Success tools — typed functions over the support_tickets / support_agents tables."""

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


def list_support_agents() -> list[dict[str, Any]]:
    """Return all support agents with their region and hire date."""
    return _rows("SELECT id, full_name, region, hired_at FROM support_agents ORDER BY full_name")


def get_support_agent(agent_id: int) -> dict[str, Any] | None:
    """Get a single support agent's profile.

    Args:
        agent_id: The support agent's integer ID.
    """
    return _row(
        "SELECT id, full_name, region, hired_at FROM support_agents WHERE id = ?", agent_id
    )


def search_support_tickets(
    status: str = "",
    priority: str = "",
    customer_id: int = 0,
    product_id: int = 0,
    limit: int = 20,
) -> list[dict[str, Any]]:
    """Search support tickets by status, priority, customer, or analytics module.

    Args:
        status: Exact status filter ('open', 'pending', 'resolved', 'closed'). Empty = no filter.
        priority: Exact priority filter ('low', 'medium', 'high', 'urgent'). Empty = no filter.
        customer_id: Filter to one business user's tickets. 0 = no filter.
        product_id: Filter to one analytics module's tickets. 0 = no filter.
        limit: Maximum results (default 20).
    """
    conditions = ["1=1"]
    params: list[Any] = []
    if status:
        conditions.append("status = ?")
        params.append(status)
    if priority:
        conditions.append("priority = ?")
        params.append(priority)
    if customer_id:
        conditions.append("customer_id = ?")
        params.append(customer_id)
    if product_id:
        conditions.append("product_id = ?")
        params.append(product_id)
    params.append(limit)
    where = " AND ".join(conditions)
    return _rows(
        f"""
        SELECT id, customer_id, product_id, agent_id, subject, priority, status,
               created_at, resolved_at, satisfaction_rating
        FROM support_tickets
        WHERE {where}
        ORDER BY created_at DESC
        LIMIT ?
        """,
        *params,
    )


def get_support_ticket(ticket_id: int) -> dict[str, Any] | None:
    """Get full details for a single support ticket, including customer and module names.

    Args:
        ticket_id: The support ticket's integer ID.
    """
    return _row(
        """
        SELECT t.id, c.full_name AS customer_name, p.name AS module_name,
               a.full_name AS agent_name, t.subject, t.priority, t.status,
               t.created_at, t.resolved_at, t.satisfaction_rating
        FROM support_tickets t
        JOIN customers c ON c.id = t.customer_id
        JOIN products p ON p.id = t.product_id
        JOIN support_agents a ON a.id = t.agent_id
        WHERE t.id = ?
        """,
        ticket_id,
    )


def get_customer_support_history(customer_id: int, limit: int = 20) -> list[dict[str, Any]]:
    """Return a business user's support ticket history, most recent first.

    Args:
        customer_id: The business user's integer ID.
        limit: Maximum tickets to return (default 20).
    """
    return _rows(
        """
        SELECT t.id, p.name AS module_name, t.subject, t.priority, t.status,
               t.created_at, t.satisfaction_rating
        FROM support_tickets t
        JOIN products p ON p.id = t.product_id
        WHERE t.customer_id = ?
        ORDER BY t.created_at DESC
        LIMIT ?
        """,
        customer_id,
        limit,
    )


def get_ticket_resolution_stats(days: int = 90) -> dict[str, Any]:
    """Aggregate ticket resolution metrics over the last N days: volume, resolution rate,
    and average time-to-resolution in hours.

    Args:
        days: Look-back window in days (default 90).
    """
    return _row(
        """
        WITH latest AS (SELECT MAX(created_at) AS max_created_at FROM support_tickets)
        SELECT
          COUNT(*) AS total_tickets,
          SUM(CASE WHEN status IN ('resolved','closed') THEN 1 ELSE 0 END) AS resolved_count,
          ROUND(100.0 * SUM(CASE WHEN status IN ('resolved','closed') THEN 1 ELSE 0 END)
                / COUNT(*), 2) AS resolution_rate_pct,
          ROUND(AVG(CASE WHEN resolved_at IS NOT NULL
                THEN (JULIANDAY(resolved_at) - JULIANDAY(created_at)) * 24 END), 2)
            AS avg_resolution_hours
        FROM support_tickets, latest
        WHERE created_at >= datetime(latest.max_created_at, ? || ' days')
        """,
        f"-{days}",
    )


def get_agent_performance(agent_id: int) -> dict[str, Any] | None:
    """Return an agent's ticket volume, resolution rate, and average CSAT.

    Args:
        agent_id: The support agent's integer ID.
    """
    return _row(
        """
        SELECT a.id, a.full_name, a.region,
               COUNT(t.id) AS total_tickets,
               SUM(CASE WHEN t.status IN ('resolved','closed') THEN 1 ELSE 0 END) AS resolved_count,
               ROUND(AVG(t.satisfaction_rating), 2) AS avg_csat
        FROM support_agents a
        LEFT JOIN support_tickets t ON t.agent_id = a.id
        WHERE a.id = ?
        GROUP BY a.id
        """,
        agent_id,
    )


def get_open_tickets_by_priority() -> list[dict[str, Any]]:
    """Return the count of currently open/pending tickets, grouped by priority."""
    return _rows(
        """
        SELECT priority, COUNT(*) AS ticket_count
        FROM support_tickets
        WHERE status IN ('open', 'pending')
        GROUP BY priority
        ORDER BY CASE priority
          WHEN 'urgent' THEN 1 WHEN 'high' THEN 2 WHEN 'medium' THEN 3 ELSE 4 END
        """
    )


def get_csat_summary(days: int = 90) -> dict[str, Any]:
    """Return average customer satisfaction (CSAT) and rating count over the last N days.

    Args:
        days: Look-back window in days (default 90).
    """
    return _row(
        """
        WITH latest AS (SELECT MAX(created_at) AS max_created_at FROM support_tickets)
        SELECT ROUND(AVG(satisfaction_rating), 2) AS avg_csat,
               COUNT(satisfaction_rating) AS rating_count
        FROM support_tickets, latest
        WHERE satisfaction_rating IS NOT NULL
          AND created_at >= datetime(latest.max_created_at, ? || ' days')
        """,
        f"-{days}",
    )
