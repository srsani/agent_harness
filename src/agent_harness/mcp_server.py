"""FastMCP server that exposes all enterprise Decision Intelligence tools over the MCP protocol.

Run standalone:
    uv run python -m agent_harness.mcp_server

Or add to an agent as an in-process MCP server:
    from agent_harness.mcp_server import mcp
    agent = Agent(model, capabilities=[MCP(mcp)])
"""

from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from agent_harness.tools import enterprise as ec
from agent_harness.tools.sql import describe_table, execute_sql, get_schema_context, list_tables

mcp = FastMCP(
    name="enterprise-decision-intel",
    instructions=(
        "Enterprise Decision Intelligence tools for testing agent performance. "
        "The database covers analytics modules, business users, subscriptions, and ratings "
        "across Finance, Supply Chain, Sales & Marketing, R&D, and HR & People. "
        "Use list_tables / describe_table to explore the schema, then "
        "execute_sql for ad-hoc queries or the typed tools for common lookups."
    ),
)

# ── schema exploration ────────────────────────────────────────────────────────

@mcp.tool()
def tool_get_schema_context() -> dict:
    """Return the full semantic layer: table meanings, column descriptions, FK relationships,
    common business metric SQL patterns, and query tips.

    Call this first when building complex queries or when you need to understand the data
    model before choosing between semantic tools and raw SQL.
    """
    return get_schema_context()


@mcp.tool()
def tool_list_tables() -> list[dict]:
    """List all tables with their semantic name, description, and column signatures."""
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


# ── catalogue (analytics modules by business function) ───────────────────────

@mcp.tool()
def tool_list_categories() -> list[dict]:
    """Return all business function categories (Finance, Supply Chain, Sales & Marketing, etc.)."""
    return ec.list_categories()


@mcp.tool()
def tool_search_products(
    query: str = "",
    category: str = "",
    max_price: float = 0.0,
    in_stock_only: bool = False,
    limit: int = 20,
) -> list[dict]:
    """Search analytics modules by keyword, business function, and annual license cost.

    Args:
        query: Text to match against module name and description.
        category: Filter by business function (partial match).
        max_price: Upper annual license cost bound in USD; 0 means no limit.
        in_stock_only: Only return modules with active deployments.
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
    """Get full details for an analytics module including average user satisfaction rating.

    Args:
        product_id: The analytics module's integer ID.
    """
    return ec.get_product(product_id)


@mcp.tool()
def tool_get_product_reviews(product_id: int, limit: int = 10) -> list[dict]:
    """Return recent user satisfaction ratings for an analytics module.

    Args:
        product_id: The analytics module's integer ID.
        limit: Maximum reviews to return (default 10).
    """
    return ec.get_product_reviews(product_id, limit=limit)


@mcp.tool()
def tool_get_top_selling_products(limit: int = 10, days: int = 90) -> list[dict]:
    """Return the most-subscribed analytics modules by activation count in the last N days.

    Args:
        limit: How many modules to return (default 10).
        days: Look-back window in days (default 90).
    """
    return ec.get_top_selling_products(limit=limit, days=days)


@mcp.tool()
def tool_get_low_stock_products(threshold: int = 30) -> list[dict]:
    """Return analytics modules with deployments at or below the threshold (low adoption alert).

    Args:
        threshold: Deployment count warning level (default 30).
    """
    return ec.get_low_stock_products(threshold=threshold)


# ── users (enterprise business users and decision-makers) ────────────────────

@mcp.tool()
def tool_get_customer(customer_id: int) -> dict | None:
    """Get a business user's profile and lifetime subscription stats.

    Args:
        customer_id: The business user's integer ID.
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
    """Search enterprise users by name, email, engagement tier, or location.

    Args:
        name: Partial name match.
        email: Partial email match.
        tier: Exact engagement tier ('standard', 'silver', 'gold').
        city: Partial city match.
        limit: Maximum results (default 20).
    """
    return ec.search_customers(name=name, email=email, tier=tier, city=city, limit=limit)


@mcp.tool()
def tool_get_customer_orders(customer_id: int, limit: int = 20) -> list[dict]:
    """Return a business user's subscription history (most recent first).

    Args:
        customer_id: The business user's integer ID.
        limit: Maximum subscriptions to return (default 20).
    """
    return ec.get_customer_orders(customer_id, limit=limit)


@mcp.tool()
def tool_get_customer_lifetime_value(customer_id: int) -> dict | None:
    """Return total spend, active subscription count, and top business function for a user.

    Args:
        customer_id: The business user's integer ID.
    """
    return ec.get_customer_lifetime_value(customer_id)


# ── subscriptions ─────────────────────────────────────────────────────────────

@mcp.tool()
def tool_get_order(order_id: int) -> dict | None:
    """Return full subscription details including all analytics modules.

    Args:
        order_id: The subscription's integer ID.
    """
    return ec.get_order(order_id)


# ── analytics ─────────────────────────────────────────────────────────────────

@mcp.tool()
def tool_get_sales_summary(start_date: str, end_date: str) -> dict:
    """Aggregate subscription revenue metrics between two ISO dates.

    Args:
        start_date: Period start, e.g. '2024-01-01'.
        end_date: Period end, e.g. '2024-03-31'.
    """
    return ec.get_sales_summary(start_date, end_date)


@mcp.tool()
def tool_get_revenue_by_month(year: int) -> list[dict]:
    """Monthly subscription revenue and activation counts for a calendar year.

    Args:
        year: Four-digit year, e.g. 2024.
    """
    return ec.get_revenue_by_month(year)


if __name__ == "__main__":
    mcp.run()
