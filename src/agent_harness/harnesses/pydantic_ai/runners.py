from __future__ import annotations

import time
from typing import Callable

from agent_harness.config import settings
from agent_harness.runners.base import AgentRunner, RunResult

HN_MCP_URL = "https://hn.caseyjhand.com/mcp"

ECOMMERCE_SYSTEM_PROMPT = (
    "You are a helpful e-commerce data analyst. "
    "Use the available tools to answer questions about products, customers, orders, and sales. "
    "Be concise and precise; always cite the data you found."
)

ECOMMERCE_SQL_SYSTEM_PROMPT = (
    "You are an expert e-commerce data analyst with direct access to a SQLite database. "
    "You have three tools: list_tables (discover what tables exist), "
    "describe_table (get column names and types for a table), "
    "and execute_sql (run any read-only SELECT query). "
    "Always start by exploring the schema if you are unsure of the structure. "
    "Write precise SQL to answer the question. Be concise and always cite the numbers you found."
)


def _optional_logfire() -> None:
    if not settings.logfire_token:
        return
    import logfire

    logfire.configure(token=settings.logfire_token)
    logfire.instrument_pydantic_ai()


def _ecommerce_tools():
    """Return all typed e-commerce tool functions for direct registration."""
    from agent_harness.tools.ecommerce import (
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
    from agent_harness.tools.sql import describe_table, execute_sql, list_tables

    return [
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


def _build_ecommerce_react_agent():
    """ReAct-style: typed tools registered directly, no CodeMode batching."""
    from pydantic_ai import Agent

    agent = Agent(_model(), system_prompt=ECOMMERCE_SYSTEM_PROMPT)
    for fn in _ecommerce_tools():
        agent.tool_plain(fn)
    return agent


def _build_ecommerce_codemode_agent():
    """Harness-style: same tools but wrapped in CodeMode — one round-trip per N calls."""
    from pydantic_ai import Agent
    from pydantic_ai_harness import CodeMode

    agent = Agent(_model(), system_prompt=ECOMMERCE_SYSTEM_PROMPT, capabilities=[CodeMode()])
    for fn in _ecommerce_tools():
        agent.tool_plain(fn)
    return agent


def _build_ecommerce_mcp_react_agent():
    """ReAct via MCP: tools served over the local FastMCP server, no CodeMode."""
    from pydantic_ai import Agent
    from pydantic_ai.capabilities import MCP

    from agent_harness.mcp_server import mcp

    return Agent(_model(), system_prompt=ECOMMERCE_SYSTEM_PROMPT, capabilities=[MCP(mcp, native=False)])


def _build_ecommerce_sql_react_agent():
    """SQL-only ReAct: model must discover the schema and write all queries itself."""
    from pydantic_ai import Agent
    from agent_harness.tools.sql import describe_table, execute_sql, list_tables

    agent = Agent(_model(), system_prompt=ECOMMERCE_SQL_SYSTEM_PROMPT)
    for fn in [list_tables, describe_table, execute_sql]:
        agent.tool_plain(fn)
    return agent


def _build_ecommerce_sql_codemode_agent():
    """SQL-only CodeMode: schema discovery + SQL generation, all batched in one sandbox run."""
    from pydantic_ai import Agent
    from pydantic_ai_harness import CodeMode
    from agent_harness.tools.sql import describe_table, execute_sql, list_tables

    agent = Agent(_model(), system_prompt=ECOMMERCE_SQL_SYSTEM_PROMPT, capabilities=[CodeMode()])
    for fn in [list_tables, describe_table, execute_sql]:
        agent.tool_plain(fn)
    return agent


def _build_ecommerce_mcp_codemode_agent():
    """Harness-style via MCP: FastMCP server tools wrapped in CodeMode."""
    from pydantic_ai import Agent
    from pydantic_ai.capabilities import MCP
    from pydantic_ai_harness import CodeMode

    from agent_harness.mcp_server import mcp

    return Agent(
        _model(),
        system_prompt=ECOMMERCE_SYSTEM_PROMPT,
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
    # ── e-commerce benchmark architectures ────────────────────────────────────
    "ecommerce-react": (
        "ReAct: 16 typed tools, one call per model turn.",
        _build_ecommerce_react_agent,
    ),
    "ecommerce-codemode": (
        "Harness/CodeMode: 16 typed tools batched inside a Monty sandbox.",
        _build_ecommerce_codemode_agent,
    ),
    "ecommerce-mcp-react": (
        "ReAct via MCP: tools served by the local FastMCP server, no batching.",
        _build_ecommerce_mcp_react_agent,
    ),
    "ecommerce-mcp-codemode": (
        "Harness via MCP: FastMCP tools wrapped in CodeMode for batched execution.",
        _build_ecommerce_mcp_codemode_agent,
    ),
    "ecommerce-sql-react": (
        "SQL-only ReAct: list_tables + describe_table + execute_sql. Model writes all queries.",
        _build_ecommerce_sql_react_agent,
    ),
    "ecommerce-sql-codemode": (
        "SQL-only CodeMode: same 3 SQL tools but schema discovery + queries run in one sandbox.",
        _build_ecommerce_sql_codemode_agent,
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
            response = agent.run_sync(prompt)
            result.output = str(response.output)
        except Exception as exc:  # noqa: BLE001 — surface harness errors in bench output
            result.error = f"{type(exc).__name__}: {exc}"
        result.elapsed_seconds = time.perf_counter() - started
        return result


def make_runner(architecture: str) -> PydanticAIRunner:
    return PydanticAIRunner(architecture)


ARCHITECTURES: dict[str, Callable[[], PydanticAIRunner]] = {
    name: (lambda n=name: make_runner(n)) for name in ARCHITECTURE_BUILDERS
}
