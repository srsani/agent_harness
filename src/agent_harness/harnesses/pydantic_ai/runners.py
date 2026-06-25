from __future__ import annotations

import asyncio
import concurrent.futures
import time
from collections.abc import Callable

from agent_harness.config import settings
from agent_harness.runners.base import AgentRunner, RunResult

HN_MCP_URL = "https://hn.caseyjhand.com/mcp"

ENTERPRISE_SYSTEM_PROMPT = (
    "You are an AI Decision Intelligence analyst for an enterprise platform. "
    "Your role is to connect siloed data across business functions — finance, supply chain, sales, "
    "R&D, HR, and operations — to deliver instant, actionable insights and recommendations. "
    "Use the available tools to answer questions about performance metrics, forecasts, resource "
    "allocation, and cross-functional KPIs. Surface patterns, flag risks, and recommend decisions "
    "with supporting evidence. Be concise and always cite the data behind every insight."
)

ENTERPRISE_SQL_SYSTEM_PROMPT = (
    "You are an expert AI Decision Intelligence analyst with direct access to "
    "an enterprise SQLite database. "
    "The database spans business functions: finance, supply chain, sales, R&D, HR, and operations. "
    "You have three tools: list_tables (discover what tables exist), "
    "describe_table (get column names and types for a table), "
    "and execute_sql (run any read-only SELECT query). "
    "Always start by exploring the schema if you are unsure of the structure. "
    "Write precise SQL to answer the question, then translate the numbers into "
    "a clear, actionable insight. Be concise and always cite the figures you found."
)


def _optional_logfire() -> None:
    if not settings.logfire_token:
        return
    import logfire

    logfire.configure(token=settings.logfire_token)
    logfire.instrument_pydantic_ai()


def _enterprise_tools():
    """Return all typed enterprise Decision Intelligence tool functions for direct registration."""
    from agent_harness.tools.enterprise import (
        get_customer,
        get_customer_lifetime_value,
        get_customer_orders,
        get_low_stock_products,
        get_order,
        get_product,
        get_product_reviews,
        get_revenue_by_month,
        get_sales_summary,
        get_top_selling_products,
        list_categories,
        search_customers,
        search_products,
    )
    from agent_harness.tools.sql import (
        describe_table,
        execute_sql,
        get_schema_context,
        list_tables,
    )

    return [
        get_schema_context,
        list_categories,
        search_products,
        get_product,
        get_product_reviews,
        get_top_selling_products,
        get_low_stock_products,
        get_customer,
        search_customers,
        get_customer_orders,
        get_customer_lifetime_value,
        get_order,
        get_sales_summary,
        get_revenue_by_month,
        list_tables,
        describe_table,
        execute_sql,
    ]


# ── architecture builders ─────────────────────────────────────────────────────

def _model():
    """Return the configured pydantic-ai model (cloud string or local OpenAIModel)."""
    return settings.build_pydantic_ai_model()


def _build_minimal_agent():
    from pydantic_ai import Agent

    return Agent(_model())


def _build_codemode_agent():
    from pydantic_ai import Agent
    from pydantic_ai_harness import CodeMode

    return Agent(_model(), capabilities=[CodeMode()])


def _build_codemode_mcp_search_agent():
    from pydantic_ai import Agent
    from pydantic_ai.capabilities import MCP, WebSearch
    from pydantic_ai_harness import CodeMode

    return Agent(
        _model(),
        capabilities=[
            CodeMode(),
            MCP(HN_MCP_URL, native=False),
            WebSearch(native=False),
        ],
    )


def _build_enterprise_react_agent():
    """ReAct-style: typed tools registered directly, no CodeMode batching."""
    from pydantic_ai import Agent

    agent = Agent(_model(), system_prompt=ENTERPRISE_SYSTEM_PROMPT)
    for fn in _enterprise_tools():
        agent.tool_plain(fn)
    return agent


def _build_enterprise_codemode_agent():
    """Harness-style: same tools but wrapped in CodeMode — one round-trip per N calls."""
    from pydantic_ai import Agent
    from pydantic_ai_harness import CodeMode

    agent = Agent(_model(), system_prompt=ENTERPRISE_SYSTEM_PROMPT, capabilities=[CodeMode()])
    for fn in _enterprise_tools():
        agent.tool_plain(fn)
    return agent


def _build_enterprise_mcp_react_agent():
    """ReAct via MCP: tools served over the local FastMCP server, no CodeMode."""
    from pydantic_ai import Agent
    from pydantic_ai.capabilities import MCP

    from agent_harness.mcp_server import mcp

    return Agent(
        _model(), system_prompt=ENTERPRISE_SYSTEM_PROMPT, capabilities=[MCP(mcp, native=False)]
    )


def _build_enterprise_sql_react_agent():
    """SQL-only ReAct: model must discover the schema and write all queries itself."""
    from pydantic_ai import Agent

    from agent_harness.tools.sql import describe_table, execute_sql, list_tables

    agent = Agent(_model(), system_prompt=ENTERPRISE_SQL_SYSTEM_PROMPT)
    for fn in [list_tables, describe_table, execute_sql]:
        agent.tool_plain(fn)
    return agent


def _build_enterprise_sql_codemode_agent():
    """SQL-only CodeMode: schema discovery + SQL generation, all batched in one sandbox run."""
    from pydantic_ai import Agent
    from pydantic_ai_harness import CodeMode

    from agent_harness.tools.sql import describe_table, execute_sql, list_tables

    agent = Agent(_model(), system_prompt=ENTERPRISE_SQL_SYSTEM_PROMPT, capabilities=[CodeMode()])
    for fn in [list_tables, describe_table, execute_sql]:
        agent.tool_plain(fn)
    return agent


def _build_enterprise_mcp_codemode_agent():
    """Harness-style via MCP: FastMCP server tools wrapped in CodeMode."""
    from pydantic_ai import Agent
    from pydantic_ai.capabilities import MCP
    from pydantic_ai_harness import CodeMode

    from agent_harness.mcp_server import mcp

    return Agent(
        _model(),
        system_prompt=ENTERPRISE_SYSTEM_PROMPT,
        capabilities=[CodeMode(), MCP(mcp, native=False)],
    )


ARCHITECTURE_BUILDERS: dict[str, tuple[str, Callable[[], object]]] = {
    # ── generic / original architectures ──────────────────────────────────────
    "minimal": (
        "Plain Pydantic AI agent with no harness capabilities.",
        _build_minimal_agent,
    ),
    "codemode": (
        "CodeMode wraps tools in a Monty-sandboxed run_code tool.",
        _build_codemode_agent,
    ),
    "codemode-mcp-search": (
        "CodeMode + Hacker News MCP + DuckDuckGo web search (native=False).",
        _build_codemode_mcp_search_agent,
    ),
    # ── enterprise Decision Intelligence benchmark architectures ──────────────
    "enterprise-react": (
        "ReAct: 17 typed tools (incl. get_schema_context), one call per model turn.",
        _build_enterprise_react_agent,
    ),
    "enterprise-codemode": (
        "Harness/CodeMode: 17 typed tools batched inside a Monty sandbox.",
        _build_enterprise_codemode_agent,
    ),
    "enterprise-mcp-react": (
        "ReAct via MCP: tools served by the local FastMCP server, no batching.",
        _build_enterprise_mcp_react_agent,
    ),
    "enterprise-mcp-codemode": (
        "Harness via MCP: FastMCP tools wrapped in CodeMode for batched execution.",
        _build_enterprise_mcp_codemode_agent,
    ),
    "enterprise-sql-react": (
        "SQL-only ReAct: list_tables + describe_table + execute_sql. Model writes all queries.",
        _build_enterprise_sql_react_agent,
    ),
    "enterprise-sql-codemode": (
        "SQL-only CodeMode: same 3 SQL tools but schema discovery + queries run in one sandbox.",
        _build_enterprise_sql_codemode_agent,
    ),
}


class PydanticAIRunner(AgentRunner):
    harness_name = "pydantic-ai"
    architecture_name: str

    def __init__(self, architecture: str) -> None:
        if architecture not in ARCHITECTURE_BUILDERS:
            raise KeyError(f"Unknown pydantic-ai architecture: {architecture}")
        self.architecture_name = architecture
        self._description, self._build_agent = ARCHITECTURE_BUILDERS[architecture]

    @property
    def description(self) -> str:
        return self._description

    def run(self, prompt: str) -> RunResult:
        result = RunResult(
            harness=self.harness_name,
            architecture=self.architecture_name,
            task="",
            prompt=prompt,
            output="",
        )
        started = time.perf_counter()
        try:
            _optional_logfire()
            agent = self._build_agent()
            # Run in a dedicated thread so we always get a fresh event loop.
            # This avoids the Python 3.12 "cannot enter context" error that
            # occurs when agent.run_sync() is called from inside Jupyter's
            # already-running event loop (even with nest_asyncio patched).
            def _run() -> str:
                return str(agent.run_sync(prompt).output)

            try:
                asyncio.get_running_loop()
                # We're inside a running loop (e.g. Jupyter) — spin a thread.
                with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                    result.output = pool.submit(_run).result()
            except RuntimeError:
                # No running loop — safe to call directly.
                result.output = _run()
        except Exception as exc:  # noqa: BLE001 — surface harness errors in bench output
            result.error = f"{type(exc).__name__}: {exc}"
        result.elapsed_seconds = time.perf_counter() - started
        return result


def make_runner(architecture: str) -> PydanticAIRunner:
    return PydanticAIRunner(architecture)


ARCHITECTURES: dict[str, Callable[[], PydanticAIRunner]] = {
    name: (lambda n=name: make_runner(n)) for name in ARCHITECTURE_BUILDERS
}
