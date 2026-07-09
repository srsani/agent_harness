"""FastMCP server(s) that expose the enterprise Decision Intelligence tools over MCP.

Two server instances are defined here:

  mcp_core — the original 17-tool surface (13 typed enterprise tools + 4 SQL tools), used by
             the `enterprise-mcp-react` / `enterprise-mcp-codemode` / `enterprise-mcp-react-native`
             architectures so they stay a stable, comparable baseline as the tool surface grows.
  mcp      — the full 120-tool surface (the same 17 plus 45 new real-domain tools and 58
             distractor tools), used by the `-120` suffixed architectures and served by default
             when this module is run standalone, since "what an external MCP client can see"
             should reflect the whole available toolset.

Run standalone (stdio, for local MCP clients; serves the full 120-tool `mcp`):
    uv run python -m agent_harness.mcp_server

Run over HTTP (required for the `enterprise-mcp-react-native` architecture — put this
behind a public tunnel, e.g. `ngrok http 8000`, and point ENTERPRISE_MCP_PUBLIC_URL at
the tunnel's `/mcp` URL):
    uv run python -m agent_harness.mcp_server --http

Or add to an agent as an in-process MCP server:
    from agent_harness.mcp_server import mcp, mcp_core
    agent = Agent(model, capabilities=[MCP(mcp_core)])  # 17-tool baseline
    agent = Agent(model, capabilities=[MCP(mcp)])        # full 120-tool surface
"""

from __future__ import annotations

import inspect
import sys

from mcp.server.fastmcp import FastMCP

from agent_harness.tools import (
    distractors,
    enterprise as ec,
    finance_ops,
    marketing,
    procurement,
    support,
    workforce,
)
from agent_harness.tools.sql import describe_table, execute_sql, get_schema_context, list_tables

mcp_core = FastMCP(
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

@mcp_core.tool()
def tool_get_schema_context() -> dict:
    """Return the full semantic layer: table meanings, column descriptions, FK relationships,
    common business metric SQL patterns, and query tips.

    Call this first when building complex queries or when you need to understand the data
    model before choosing between semantic tools and raw SQL.
    """
    return get_schema_context()


@mcp_core.tool()
def tool_list_tables() -> list[dict]:
    """List all tables with their semantic name, description, and column signatures."""
    return list_tables()


@mcp_core.tool()
def tool_describe_table(table_name: str) -> list[dict]:
    """Return column definitions for a table.

    Args:
        table_name: Exact table name (e.g. 'orders').
    """
    return describe_table(table_name)


@mcp_core.tool()
def tool_execute_sql(query: str, limit: int = 100) -> dict:
    """Run a read-only SELECT statement and return results.

    Args:
        query: A valid SQLite SELECT statement.
        limit: Row cap if no LIMIT clause present (default 100).
    """
    return execute_sql(query, limit=limit)


# ── catalogue (analytics modules by business function) ───────────────────────

@mcp_core.tool()
def tool_list_categories() -> list[dict]:
    """Return all business function categories (Finance, Supply Chain, Sales & Marketing, etc.)."""
    return ec.list_categories()


@mcp_core.tool()
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


@mcp_core.tool()
def tool_get_product(product_id: int) -> dict | None:
    """Get full details for an analytics module including average user satisfaction rating.

    Args:
        product_id: The analytics module's integer ID.
    """
    return ec.get_product(product_id)


@mcp_core.tool()
def tool_get_product_reviews(product_id: int, limit: int = 10) -> list[dict]:
    """Return recent user satisfaction ratings for an analytics module.

    Args:
        product_id: The analytics module's integer ID.
        limit: Maximum reviews to return (default 10).
    """
    return ec.get_product_reviews(product_id, limit=limit)


@mcp_core.tool()
def tool_get_top_selling_products(limit: int = 10, days: int = 90) -> list[dict]:
    """Return analytics modules with the most subscription activations in the last N days.

    Activation count is distinct non-cancelled subscriptions/orders, not purchased seats.

    Args:
        limit: How many modules to return (default 10).
        days: Look-back window in days (default 90).
    """
    return ec.get_top_selling_products(limit=limit, days=days)


@mcp_core.tool()
def tool_get_low_stock_products(threshold: int = 30) -> list[dict]:
    """Return analytics modules with deployments at or below the threshold (low adoption alert).

    Args:
        threshold: Deployment count warning level (default 30).
    """
    return ec.get_low_stock_products(threshold=threshold)


# ── users (enterprise business users and decision-makers) ────────────────────

@mcp_core.tool()
def tool_get_customer(customer_id: int) -> dict | None:
    """Get a business user's profile and lifetime subscription stats.

    Args:
        customer_id: The business user's integer ID.
    """
    return ec.get_customer(customer_id)


@mcp_core.tool()
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


@mcp_core.tool()
def tool_get_customer_orders(customer_id: int, limit: int = 20) -> list[dict]:
    """Return a business user's subscription history (most recent first).

    Args:
        customer_id: The business user's integer ID.
        limit: Maximum subscriptions to return (default 20).
    """
    return ec.get_customer_orders(customer_id, limit=limit)


@mcp_core.tool()
def tool_get_customer_lifetime_value(customer_id: int) -> dict | None:
    """Return total spend, active subscription count, and top business function for a user.

    Args:
        customer_id: The business user's integer ID.
    """
    return ec.get_customer_lifetime_value(customer_id)


# ── subscriptions ─────────────────────────────────────────────────────────────

@mcp_core.tool()
def tool_get_order(order_id: int) -> dict | None:
    """Return full subscription details including all analytics modules.

    Args:
        order_id: The subscription's integer ID.
    """
    return ec.get_order(order_id)


# ── analytics ─────────────────────────────────────────────────────────────────

@mcp_core.tool()
def tool_get_sales_summary(start_date: str, end_date: str) -> dict:
    """Aggregate subscription revenue metrics between two ISO dates.

    Args:
        start_date: Period start, e.g. '2024-01-01'.
        end_date: Period end, e.g. '2024-03-31'.
    """
    return ec.get_sales_summary(start_date, end_date)


@mcp_core.tool()
def tool_get_revenue_by_month(year: int) -> list[dict]:
    """Monthly subscription revenue and activation counts for a calendar year.

    Args:
        year: Four-digit year, e.g. 2024.
    """
    return ec.get_revenue_by_month(year)


# ── mcp: the full 120-tool surface ─────────────────────────────────────────────
# The original 17 tools (re-registered here from their plain functions, not the `mcp_core`
# decorator wrappers -- FastMCP tools aren't transferable between server instances) plus 45
# new real-domain tools and 58 distractor tools. Registered programmatically via `add_tool`
# (which derives name/schema straight from each function's signature and docstring) rather
# than one hand-written `@mcp.tool()` wrapper per function like `mcp_core` above -- identical
# behavior, far less boilerplate at 120 tools.

mcp = FastMCP(
    name="enterprise-decision-intel-120",
    instructions=(
        mcp_core.instructions
        + " This server additionally exposes Support & Success, Marketing Campaigns, "
        "Procurement/Suppliers, Workforce/HR, and Finance/Budgets tools, alongside a large "
        "number of decoy tools that are never the right choice for a real question -- "
        "read each tool's description carefully before choosing one."
    ),
)

_CORE_TOOL_FUNCTIONS = [
    get_schema_context,
    list_tables,
    describe_table,
    execute_sql,
    ec.list_categories,
    ec.search_products,
    ec.get_product,
    ec.get_product_reviews,
    ec.get_top_selling_products,
    ec.get_low_stock_products,
    ec.get_customer,
    ec.search_customers,
    ec.get_customer_orders,
    ec.get_customer_lifetime_value,
    ec.get_order,
    ec.get_sales_summary,
    ec.get_revenue_by_month,
]
_SCALE_OUT_MODULES = (support, marketing, procurement, workforce, finance_ops, distractors)


def _register_120_tools() -> None:
    for fn in _CORE_TOOL_FUNCTIONS:
        mcp.add_tool(fn, name=f"tool_{fn.__name__}")
    for module in _SCALE_OUT_MODULES:
        for name, fn in inspect.getmembers(module, inspect.isfunction):
            if name.startswith("_") or fn.__module__ != module.__name__:
                continue
            mcp.add_tool(fn, name=f"tool_{name}")


_register_120_tools()


if __name__ == "__main__":
    if "--http" in sys.argv:
        mcp.run(transport="streamable-http")
    else:
        mcp.run()
