"""FastMCP server that exposes all e-commerce tools over the MCP protocol.

Run standalone:
    uv run python -m agent_harness.mcp_server

Or add to an agent as an in-process MCP server:
    from agent_harness.mcp_server import mcp
    agent = Agent(model, capabilities=[MCP(mcp)])
"""

from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from agent_harness.tools import ecommerce as ec
from agent_harness.tools.sql import describe_table, execute_sql, list_tables

mcp = FastMCP(
    name="ecommerce-bench",
    instructions=(
        "E-commerce database tools for testing agent performance. "
        "Use list_tables / describe_table to explore the schema, then "
        "execute_sql for ad-hoc queries or the typed tools for common lookups."
    ),
)

# ── schema exploration ────────────────────────────────────────────────────────

@mcp.tool()
def tool_list_tables() -> list[dict]:
    """List all database tables and their column signatures."""
    return list_tables()


@mcp.tool()
def tool_describe_table(table_name: str) -> list[dict]:
    """Return column definitions for a table.

    Args:
        table_name: Exact table name (e.g. 'orders').
    """
    return describe_table(table_name)


@mcp.tool()
def tool_execute_sql(query: str, limit: int = 100) -> dict:
    """Run a read-only SELECT statement and return results.

    Args:
        query: A valid SQLite SELECT statement.
        limit: Row cap if no LIMIT clause present (default 100).
    """
    return execute_sql(query, limit=limit)


# ── catalogue ─────────────────────────────────────────────────────────────────

@mcp.tool()
def tool_list_categories() -> list[dict]:
    """Return all product categories."""
    return ec.list_categories()


@mcp.tool()
def tool_search_products(
    query: str = "",
    category: str = "",
    max_price: float = 0.0,
    in_stock_only: bool = False,
    limit: int = 20,
) -> list[dict]:
    """Search products by keyword, category, and price.

    Args:
        query: Text to match against product name and description.
        category: Filter by category name (partial match).
        max_price: Upper price bound; 0 means no limit.
        in_stock_only: Only return products currently in stock.
        limit: Maximum results (default 20).
    """
    return ec.search_products(
        query=query,
        category=category,
        max_price=max_price,
        in_stock_only=in_stock_only,
        limit=limit,
    )


@mcp.tool()
def tool_get_product(product_id: int) -> dict | None:
    """Get full details for a product including average rating.

    Args:
        product_id: The product's integer ID.
    """
    return ec.get_product(product_id)


@mcp.tool()
def tool_get_product_reviews(product_id: int, limit: int = 10) -> list[dict]:
    """Return recent reviews for a product.

    Args:
        product_id: The product's integer ID.
        limit: Maximum reviews to return (default 10).
    """
    return ec.get_product_reviews(product_id, limit=limit)


@mcp.tool()
def tool_get_top_selling_products(limit: int = 10, days: int = 90) -> list[dict]:
    """Return top-selling products by units sold in the last N days.

    Args:
        limit: How many products to return (default 10).
        days: Look-back window in days (default 90).
    """
    return ec.get_top_selling_products(limit=limit, days=days)


@mcp.tool()
def tool_get_low_stock_products(threshold: int = 30) -> list[dict]:
    """Return products with stock at or below the threshold.

    Args:
        threshold: Stock warning level (default 30).
    """
    return ec.get_low_stock_products(threshold=threshold)


# ── customers ─────────────────────────────────────────────────────────────────

@mcp.tool()
def tool_get_customer(customer_id: int) -> dict | None:
    """Get a customer's profile and lifetime order stats.

    Args:
        customer_id: The customer's integer ID.
    """
    return ec.get_customer(customer_id)


@mcp.tool()
def tool_search_customers(
    name: str = "",
    email: str = "",
    tier: str = "",
    city: str = "",
    limit: int = 20,
) -> list[dict]:
    """Search customers by name, email, tier, or city.

    Args:
        name: Partial name match.
        email: Partial email match.
        tier: Exact tier ('standard', 'silver', 'gold').
        city: Partial city match.
        limit: Maximum results (default 20).
    """
    return ec.search_customers(name=name, email=email, tier=tier, city=city, limit=limit)


@mcp.tool()
def tool_get_customer_orders(customer_id: int, limit: int = 20) -> list[dict]:
    """Return a customer's order history (most recent first).

    Args:
        customer_id: The customer's integer ID.
        limit: Maximum orders to return (default 20).
    """
    return ec.get_customer_orders(customer_id, limit=limit)


@mcp.tool()
def tool_get_customer_lifetime_value(customer_id: int) -> dict | None:
    """Return total spend, delivered order count, and favourite category for a customer.

    Args:
        customer_id: The customer's integer ID.
    """
    return ec.get_customer_lifetime_value(customer_id)


# ── orders ─────────────────────────────────────────────────────────────────────

@mcp.tool()
def tool_get_order(order_id: int) -> dict | None:
    """Return full order details including all line items.

    Args:
        order_id: The order's integer ID.
    """
    return ec.get_order(order_id)


# ── analytics ─────────────────────────────────────────────────────────────────

@mcp.tool()
def tool_get_sales_summary(start_date: str, end_date: str) -> dict:
    """Aggregate sales metrics between two ISO dates.

    Args:
        start_date: Period start, e.g. '2024-01-01'.
        end_date: Period end, e.g. '2024-03-31'.
    """
    return ec.get_sales_summary(start_date, end_date)


@mcp.tool()
def tool_get_revenue_by_month(year: int) -> list[dict]:
    """Monthly revenue and order counts for a calendar year.

    Args:
        year: Four-digit year, e.g. 2024.
    """
    return ec.get_revenue_by_month(year)


if __name__ == "__main__":
    mcp.run()
