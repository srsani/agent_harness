"""Typed, semantic tools that wrap the e-commerce database.

These are the "rich" tools a harness-based agent would get.
Each function returns plain Python dicts/lists so they work as
pydantic-ai tools, MCP tools, or standalone callables.
"""

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


# ── catalogue ─────────────────────────────────────────────────────────────────

def list_categories() -> list[dict[str, Any]]:
    """Return all product categories."""
    return _rows("SELECT id, name, description FROM categories ORDER BY name")


def search_products(
    query: str = "",
    category: str = "",
    max_price: float = 0.0,
    in_stock_only: bool = False,
    limit: int = 20,
) -> list[dict[str, Any]]:
    """Search products by keyword, optional category name filter, and optional max price.

    Args:
        query: Free-text search against product name and description.
        category: Filter by category name (partial match, case-insensitive).
        max_price: Upper price bound. 0 means no limit.
        in_stock_only: If True, only return products with stock_quantity > 0.
        limit: Maximum number of results to return (default 20).
    """
    conditions = ["1=1"]
    params: list[Any] = []

    if query:
        conditions.append("(p.name LIKE ? OR p.description LIKE ?)")
        params += [f"%{query}%", f"%{query}%"]
    if category:
        conditions.append("c.name LIKE ?")
        params.append(f"%{category}%")
    if max_price > 0:
        conditions.append("p.price <= ?")
        params.append(max_price)
    if in_stock_only:
        conditions.append("p.stock_quantity > 0")

    params.append(limit)
    where = " AND ".join(conditions)
    return _rows(
        f"""
        SELECT p.id, p.name, p.description, p.price, p.stock_quantity,
               c.name AS category
        FROM products p
        JOIN categories c ON c.id = p.category_id
        WHERE {where}
        ORDER BY p.name
        LIMIT ?
        """,
        *params,
    )


def get_product(product_id: int) -> dict[str, Any] | None:
    """Get full details for a single product, including its category and average rating."""
    return _row(
        """
        SELECT p.id, p.name, p.description, p.price, p.stock_quantity,
               c.name AS category,
               ROUND(AVG(r.rating), 2) AS avg_rating,
               COUNT(r.id) AS review_count
        FROM products p
        JOIN categories c ON c.id = p.category_id
        LEFT JOIN reviews r ON r.product_id = p.id
        WHERE p.id = ?
        GROUP BY p.id
        """,
        product_id,
    )


def get_product_reviews(product_id: int, limit: int = 10) -> list[dict[str, Any]]:
    """Return the most recent reviews for a product.

    Args:
        product_id: Product to fetch reviews for.
        limit: Maximum number of reviews (default 10).
    """
    return _rows(
        """
        SELECT r.rating, r.title, r.body, r.created_at,
               c.full_name AS reviewer
        FROM reviews r
        JOIN customers c ON c.id = r.customer_id
        WHERE r.product_id = ?
        ORDER BY r.created_at DESC
        LIMIT ?
        """,
        product_id,
        limit,
    )


def get_top_selling_products(limit: int = 10, days: int = 90) -> list[dict[str, Any]]:
    """Return best-selling products by units sold in the last N days.

    Args:
        limit: How many products to return (default 10).
        days: Look-back window in days (default 90).
    """
    return _rows(
        """
        SELECT p.id, p.name, p.price,
               c.name AS category,
               SUM(oi.quantity) AS units_sold,
               SUM(oi.quantity * oi.unit_price) AS revenue
        FROM order_items oi
        JOIN orders o   ON o.id  = oi.order_id
        JOIN products p ON p.id  = oi.product_id
        JOIN categories c ON c.id = p.category_id
        WHERE o.created_at >= datetime('now', ? || ' days')
          AND o.status != 'cancelled'
        GROUP BY p.id
        ORDER BY units_sold DESC
        LIMIT ?
        """,
        f"-{days}",
        limit,
    )


def get_low_stock_products(threshold: int = 30) -> list[dict[str, Any]]:
    """Return products whose stock_quantity is at or below the threshold.

    Args:
        threshold: Stock quantity warning level (default 30).
    """
    return _rows(
        """
        SELECT p.id, p.name, p.price, p.stock_quantity,
               c.name AS category
        FROM products p
        JOIN categories c ON c.id = p.category_id
        WHERE p.stock_quantity <= ?
        ORDER BY p.stock_quantity ASC
        """,
        threshold,
    )


# ── customers ─────────────────────────────────────────────────────────────────

def get_customer(customer_id: int) -> dict[str, Any] | None:
    """Get a customer's profile including lifetime order stats."""
    return _row(
        """
        SELECT c.id, c.full_name, c.email, c.city, c.country, c.tier, c.created_at,
               COUNT(o.id)          AS total_orders,
               ROUND(SUM(o.total_amount), 2) AS lifetime_value
        FROM customers c
        LEFT JOIN orders o ON o.customer_id = c.id AND o.status != 'cancelled'
        WHERE c.id = ?
        GROUP BY c.id
        """,
        customer_id,
    )


def search_customers(
    name: str = "",
    email: str = "",
    tier: str = "",
    city: str = "",
    limit: int = 20,
) -> list[dict[str, Any]]:
    """Search customers by name, email, tier, or city.

    Args:
        name: Partial name match (case-insensitive).
        email: Partial email match.
        tier: Exact tier match ('standard', 'silver', or 'gold').
        city: Partial city match.
        limit: Maximum results (default 20).
    """
    conditions = ["1=1"]
    params: list[Any] = []
    if name:
        conditions.append("full_name LIKE ?")
        params.append(f"%{name}%")
    if email:
        conditions.append("email LIKE ?")
        params.append(f"%{email}%")
    if tier:
        conditions.append("tier = ?")
        params.append(tier)
    if city:
        conditions.append("city LIKE ?")
        params.append(f"%{city}%")
    params.append(limit)
    where = " AND ".join(conditions)
    return _rows(
        f"SELECT id, full_name, email, city, country, tier, created_at"
        f" FROM customers WHERE {where} ORDER BY full_name LIMIT ?",
        *params,
    )


def get_customer_orders(customer_id: int, limit: int = 20) -> list[dict[str, Any]]:
    """Return a customer's order history (most recent first).

    Args:
        customer_id: Customer to look up.
        limit: Maximum number of orders to return (default 20).
    """
    return _rows(
        """
        SELECT o.id, o.status, o.total_amount, o.created_at, o.shipped_at,
               COUNT(oi.id) AS item_count
        FROM orders o
        JOIN order_items oi ON oi.order_id = o.id
        WHERE o.customer_id = ?
        GROUP BY o.id
        ORDER BY o.created_at DESC
        LIMIT ?
        """,
        customer_id,
        limit,
    )


def get_customer_lifetime_value(customer_id: int) -> dict[str, Any] | None:
    """Detailed lifetime-value breakdown for a customer: orders, spend, and top category."""
    return _row(
        """
        SELECT c.id, c.full_name, c.tier,
               COUNT(DISTINCT o.id)           AS delivered_orders,
               ROUND(SUM(oi.quantity * oi.unit_price), 2) AS total_spend,
               (
                   SELECT cat.name
                   FROM order_items oi2
                   JOIN orders o2 ON o2.id = oi2.order_id
                   JOIN products p2 ON p2.id = oi2.product_id
                   JOIN categories cat ON cat.id = p2.category_id
                   WHERE o2.customer_id = c.id AND o2.status = 'delivered'
                   GROUP BY cat.id
                   ORDER BY SUM(oi2.quantity * oi2.unit_price) DESC
                   LIMIT 1
               ) AS favourite_category
        FROM customers c
        JOIN orders o    ON o.customer_id   = c.id
        JOIN order_items oi ON oi.order_id  = o.id
        WHERE c.id = ? AND o.status = 'delivered'
        GROUP BY c.id
        """,
        customer_id,
    )


# ── orders ─────────────────────────────────────────────────────────────────────

def get_order(order_id: int) -> dict[str, Any] | None:
    """Get order header (status, total, dates) plus its line items."""
    header = _row(
        """
        SELECT o.id, o.status, o.total_amount, o.created_at, o.shipped_at,
               c.id AS customer_id, c.full_name AS customer_name
        FROM orders o
        JOIN customers c ON c.id = o.customer_id
        WHERE o.id = ?
        """,
        order_id,
    )
    if header is None:
        return None
    items = _rows(
        """
        SELECT p.id AS product_id, p.name AS product_name,
               oi.quantity, oi.unit_price,
               ROUND(oi.quantity * oi.unit_price, 2) AS line_total
        FROM order_items oi
        JOIN products p ON p.id = oi.product_id
        WHERE oi.order_id = ?
        ORDER BY p.name
        """,
        order_id,
    )
    return {**header, "items": items}


# ── analytics ─────────────────────────────────────────────────────────────────

def get_sales_summary(start_date: str, end_date: str) -> dict[str, Any]:
    """Aggregate sales metrics between two ISO-8601 dates (inclusive).

    Args:
        start_date: Start of the period, e.g. '2024-01-01'.
        end_date: End of the period, e.g. '2024-03-31'.
    """
    row = _row(
        """
        SELECT COUNT(DISTINCT o.id)                             AS total_orders,
               COUNT(DISTINCT o.customer_id)                    AS unique_customers,
               ROUND(SUM(o.total_amount), 2)                   AS total_revenue,
               ROUND(AVG(o.total_amount), 2)                   AS avg_order_value,
               SUM(oi.quantity)                                 AS units_sold
        FROM orders o
        JOIN order_items oi ON oi.order_id = o.id
        WHERE o.created_at BETWEEN ? AND ?
          AND o.status != 'cancelled'
        """,
        start_date,
        end_date + "T23:59:59",
    )
    by_category = _rows(
        """
        SELECT c.name AS category,
               SUM(oi.quantity * oi.unit_price) AS revenue,
               SUM(oi.quantity) AS units
        FROM order_items oi
        JOIN orders o ON o.id = oi.order_id
        JOIN products p ON p.id = oi.product_id
        JOIN categories c ON c.id = p.category_id
        WHERE o.created_at BETWEEN ? AND ?
          AND o.status != 'cancelled'
        GROUP BY c.id
        ORDER BY revenue DESC
        """,
        start_date,
        end_date + "T23:59:59",
    )
    return {**(row or {}), "by_category": by_category}


def get_revenue_by_month(year: int) -> list[dict[str, Any]]:
    """Return monthly revenue and order counts for a given calendar year.

    Args:
        year: Four-digit year, e.g. 2024.
    """
    return _rows(
        """
        SELECT strftime('%Y-%m', created_at) AS month,
               COUNT(id)                      AS orders,
               ROUND(SUM(total_amount), 2)   AS revenue
        FROM orders
        WHERE strftime('%Y', created_at) = ?
          AND status != 'cancelled'
        GROUP BY month
        ORDER BY month
        """,
        str(year),
    )
