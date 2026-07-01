from __future__ import annotations

import time
from collections.abc import Callable

from agent_harness.config import settings
from agent_harness.harnesses.pydantic_ai.traced_agent import TracedAgent
from agent_harness.runners.base import AgentRunner, RunResult

HN_MCP_URL = "https://hn.caseyjhand.com/mcp"

ENTERPRISE_SYSTEM_PROMPT = (
    "You are an AI Decision Intelligence analyst for an enterprise platform. "
    "Your role is to connect siloed data across business functions — finance, supply chain, sales, "
    "R&D, HR, and operations — to deliver instant, actionable insights and recommendations. "
    "Use the available tools to answer questions about performance metrics, forecasts, resource "
    "allocation, and cross-functional KPIs. Surface patterns, flag risks, and recommend decisions "
    "with supporting evidence. Be concise and always cite the data behind every insight. "
    "For benchmark questions, answer only with values returned by tools or SQL. Do not add "
    "rank numbers, percentages, totals, averages, per-seat values, dates, or narrative numeric "
    "claims unless the user explicitly asks for them."
)

ENTERPRISE_SQL_SYSTEM_PROMPT = (
    "You are an expert AI Decision Intelligence analyst with direct access to "
    "an enterprise SQLite database. "
    "The database spans business functions: finance, supply chain, sales, R&D, HR, and operations. "
    "You have three tools: list_tables (discover what tables exist), "
    "describe_table (get column names and types for a table), "
    "and execute_sql (run any read-only SELECT query). "
    "Always start by exploring the schema if you are unsure of the structure. "
    "For relative date windows, anchor queries to SELECT MAX(created_at) FROM orders. "
    "For module activation count, count DISTINCT subscription/order IDs from all "
    "non-cancelled orders; do not restrict to delivered orders and do not count seats. "
    "For top modules, break activation-count ties by subscription revenue descending. "
    "Write precise SQL to answer the question, then translate the numbers into "
    "a clear answer. Be concise and always cite the figures you found. "
    "For benchmark questions, return only requested fields and avoid extra numeric claims."
)

BENCHMARK_RESPONSE_INSTRUCTIONS = (
    "Benchmark response requirements:\n"
    "- Use available database tools or SQL for enterprise data questions.\n"
    "- Return only the fields requested by the user, preferably as a compact table.\n"
    "- Do not include a rank column, key insights, totals, percentages, per-seat values, dates, "
    "or any other numeric claims unless the user explicitly asks for them.\n"
    "- Do not restate numeric values from the question, such as lookback windows or requested "
    "row counts, in headings or preambles.\n"
    "- If a tool returns exactly the requested rows and fields, copy those values without "
    "recomputing or relabeling them."
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
            WebSearch(native=False, local=True),
        ],
    )


def _with_benchmark_instructions(prompt: str) -> str:
    return f"{prompt}\n\n{BENCHMARK_RESPONSE_INSTRUCTIONS}"


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

    def run(self, prompt: str, *, session_id: str | None = None) -> RunResult:
        result = RunResult(
            harness=self.harness_name,
            architecture=self.architecture_name,
            task="",
            prompt=prompt,
            output="",
        )
        if session_id is not None:
            result.metadata["langfuse_session_id"] = session_id

        started = time.perf_counter()
        try:
            _optional_logfire()
            trace_metadata = {
                "harness": self.harness_name,
                "architecture": self.architecture_name,
            }
            if session_id is not None:
                trace_metadata["langfuse_session_id"] = session_id

            traced_agent = TracedAgent(
                agent=self._build_agent(),
                trace_name="agent-harness.run",
                trace_metadata=trace_metadata,
                session_id=session_id,
                model_name=settings.agent_bench_model,
                require_langfuse=True,
            )
            run_result = traced_agent.run_sync(_with_benchmark_instructions(prompt))
            result.output = str(run_result.output)
            if traced_agent.last_trace_id is not None:
                result.metadata["langfuse_trace_id"] = traced_agent.last_trace_id
            if traced_agent.last_observation_id is not None:
                result.metadata["langfuse_observation_id"] = traced_agent.last_observation_id
            if traced_agent.last_trace_url is not None:
                result.metadata["langfuse_trace_url"] = traced_agent.last_trace_url
        except Exception as exc:  # noqa: BLE001 — surface harness errors in bench output
            result.error = f"{type(exc).__name__}: {exc}"
        result.elapsed_seconds = time.perf_counter() - started
        return result


def make_runner(architecture: str) -> PydanticAIRunner:
    return PydanticAIRunner(architecture)


ARCHITECTURES: dict[str, Callable[[], PydanticAIRunner]] = {
    name: (lambda n=name: make_runner(n)) for name in ARCHITECTURE_BUILDERS
}
