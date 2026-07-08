from __future__ import annotations

import time
from collections.abc import Callable

from agent_harness.config import settings
from agent_harness.harnesses.pydantic_ai.traced_agent import TracedAgent
from agent_harness.runners.base import AgentRunner, RunResult

HN_MCP_URL = "https://hn.caseyjhand.com/mcp"

# Pinned low-temperature sampling: reduces (but per pydantic-ai's own docs, does not
# fully eliminate) run-to-run variance in tool selection, generated CodeMode sandbox
# scripts, and answer wording. `seed` is intentionally omitted here -- it is only
# honored by OpenAI/Groq/Cohere/Mistral/Gemini/xAI, not Anthropic, which is the
# default `agent_bench_model`; switch providers if full seed-based reproducibility
# is required.
_MODEL_SETTINGS = {"temperature": 0.0}

# CodeMode's `run_code` tool caps itself at 3 retries by default (syntax/type errors
# count as retries). Under non-zero-temperature sampling, an unlucky streak of bad
# generated sandbox code can exhaust that budget and fail the whole run outright
# (`UnexpectedModelBehavior: Tool 'run_code' exceeded max retries count of 3`).
# Raising it gives the model more chances to self-correct before giving up.
_CODE_MODE_MAX_RETRIES = 6

# Anthropic's extended thinking (and most reasoning-effort APIs) reject a pinned
# `temperature=0` — thinking requires the provider's own sampling behavior. The
# `Thinking` capability variants below intentionally omit the `temperature` pin used
# everywhere else in this file, at the cost of the extra determinism that pin buys.
_THINKING_MODEL_SETTINGS: dict = {}

# pydantic-ai defaults a tool's own retry budget to 1: a single bad-argument call (e.g.
# a string where an int is expected) raises `ModelRetry` once, and a second miss fails
# the whole run with `UnexpectedModelBehavior: Tool '...' exceeded max retries count of
# 1`. That's tight for smaller/local models, and especially for CodeMode, where the
# tool call happens indirectly through model-generated Python rather than a
# schema-validated tool-call block. Same motivation as `_CODE_MODE_MAX_RETRIES` above:
# give the model more chances to self-correct before giving up.
_TOOL_RETRIES = 3

ENTERPRISE_SYSTEM_PROMPT = (
    "You are an AI Decision Intelligence analyst for an enterprise platform. "
    "Your role is to connect siloed data across business functions — finance, supply chain, sales, "
    "R&D, HR, and operations — to deliver instant, actionable insights and recommendations. "
    "Use the available tools to answer questions about performance metrics, forecasts, resource "
    "allocation, and cross-functional KPIs. Surface patterns, flag risks, and recommend decisions "
    "with supporting evidence. Be concise and always cite the data behind every insight. "
    "For benchmark questions, answer only with values returned by tools or SQL. Do not add "
    "rank numbers, percentages, totals, averages, per-seat values, dates, or narrative numeric "
    "claims unless the user explicitly asks for them. "
    "A tool's returned rows are already unique and already sorted/filtered per its documented "
    "parameters (e.g. by count or date window) — copy each row's values verbatim into your answer "
    "exactly once. Do not re-sort, re-filter, re-aggregate, deduplicate, or recompute a tool's "
    "numeric fields yourself, and never repeat the same entity (e.g. the same module name and "
    "business function) more than once in a single answer."
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
    "For benchmark questions, return only requested fields and avoid extra numeric claims. "
    "Copy each row your SQL returns verbatim into the answer exactly once — do not re-sort, "
    "re-filter, re-aggregate, or recompute values client-side, and never repeat the same row "
    "(e.g. the same module name and business function) more than once in a single answer."
)

BENCHMARK_RESPONSE_INSTRUCTIONS = (
    "Benchmark response requirements:\n"
    "- Use available database tools or SQL for enterprise data questions.\n"
    "- Return only the fields requested by the user, preferably as a compact table.\n"
    "- Do not include a rank column, key insights, totals, percentages, per-seat values, dates, "
    "or any other numeric claims unless the user explicitly asks for them.\n"
    "- Do not restate numeric values from the question, such as lookback windows or requested "
    "row counts, in headings or preambles.\n"
    "- If a tool or query returns exactly the requested rows and fields, copy those values "
    "verbatim, in the same order, exactly once each — do not recompute, relabel, re-sort, "
    "re-aggregate, or duplicate any row."
)


def _optional_logfire() -> None:
    if not settings.logfire_token:
        return
    import logfire

    logfire.configure(token=settings.logfire_token)
    logfire.instrument_pydantic_ai()


def _retryable(fn):
    """Wrap a tool function so any exception it raises becomes a `pydantic_ai.ModelRetry`.

    `sql.py`'s tools raise a plain `SQLError` (e.g. bad SQL syntax, unknown table) so they
    stay usable as framework-agnostic callables (MCP tools, notebook cells, standalone
    scripts). But pydantic-ai's tool-call retry machinery only treats `ValidationError`/
    `ModelRetry` as retryable -- any other exception propagates straight up and kills the
    whole run instantly, regardless of the `retries=` budget on the `Agent`. This wrapper
    bridges that gap at the harness registration layer instead of coupling `sql.py` itself
    to pydantic-ai. `functools.wraps` preserves `__name__`/`__doc__`/signature so
    pydantic-ai still derives the correct tool schema from the wrapped function.
    """
    from functools import wraps

    from pydantic_ai import ModelRetry

    @wraps(fn)
    def wrapper(*args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except ModelRetry:
            raise
        except Exception as exc:  # noqa: BLE001 -- any tool-raised error becomes a retry
            raise ModelRetry(str(exc)) from exc

    return wrapper


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

    describe_table = _retryable(describe_table)
    execute_sql = _retryable(execute_sql)

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

    return Agent(_model(), model_settings=_MODEL_SETTINGS)


def _build_codemode_agent():
    from pydantic_ai import Agent
    from pydantic_ai_harness import CodeMode

    return Agent(
        _model(),
        capabilities=[CodeMode(max_retries=_CODE_MODE_MAX_RETRIES)],
        model_settings=_MODEL_SETTINGS,
    )


def _build_codemode_mcp_search_agent():
    from pydantic_ai import Agent
    from pydantic_ai.capabilities import MCP, WebSearch
    from pydantic_ai_harness import CodeMode

    return Agent(
        _model(),
        capabilities=[
            CodeMode(max_retries=_CODE_MODE_MAX_RETRIES),
            MCP(HN_MCP_URL, native=False),
            WebSearch(native=False, local=True),
        ],
        model_settings=_MODEL_SETTINGS,
    )


def _with_benchmark_instructions(prompt: str) -> str:
    return f"{prompt}\n\n{BENCHMARK_RESPONSE_INSTRUCTIONS}"


def _build_enterprise_react_agent():
    """ReAct-style: typed tools registered directly, no CodeMode batching."""
    from pydantic_ai import Agent

    agent = Agent(
        _model(),
        system_prompt=ENTERPRISE_SYSTEM_PROMPT,
        model_settings=_MODEL_SETTINGS,
        retries=_TOOL_RETRIES,
    )
    for fn in _enterprise_tools():
        agent.tool_plain(fn)
    return agent


def _build_enterprise_codemode_agent():
    """Harness-style: same tools but wrapped in CodeMode — one round-trip per N calls."""
    from pydantic_ai import Agent
    from pydantic_ai_harness import CodeMode

    agent = Agent(
        _model(),
        system_prompt=ENTERPRISE_SYSTEM_PROMPT,
        capabilities=[CodeMode(max_retries=_CODE_MODE_MAX_RETRIES)],
        model_settings=_MODEL_SETTINGS,
        retries=_TOOL_RETRIES,
    )
    for fn in _enterprise_tools():
        agent.tool_plain(fn)
    return agent


def _build_enterprise_mcp_react_agent():
    """ReAct via MCP: tools served over the local FastMCP server, no CodeMode."""
    from pydantic_ai import Agent
    from pydantic_ai.capabilities import MCP

    from agent_harness.mcp_server import mcp

    return Agent(
        _model(),
        system_prompt=ENTERPRISE_SYSTEM_PROMPT,
        capabilities=[MCP(mcp, native=False)],
        model_settings=_MODEL_SETTINGS,
        retries=_TOOL_RETRIES,
    )


def _build_enterprise_sql_react_agent():
    """SQL-only ReAct: model must discover the schema and write all queries itself."""
    from pydantic_ai import Agent

    from agent_harness.tools.sql import describe_table, execute_sql, list_tables

    agent = Agent(
        _model(),
        system_prompt=ENTERPRISE_SQL_SYSTEM_PROMPT,
        model_settings=_MODEL_SETTINGS,
        retries=_TOOL_RETRIES,
    )
    for fn in [list_tables, _retryable(describe_table), _retryable(execute_sql)]:
        agent.tool_plain(fn)
    return agent


def _build_enterprise_sql_codemode_agent():
    """SQL-only CodeMode: schema discovery + SQL generation, all batched in one sandbox run."""
    from pydantic_ai import Agent
    from pydantic_ai_harness import CodeMode

    from agent_harness.tools.sql import describe_table, execute_sql, list_tables

    agent = Agent(
        _model(),
        system_prompt=ENTERPRISE_SQL_SYSTEM_PROMPT,
        capabilities=[CodeMode(max_retries=_CODE_MODE_MAX_RETRIES)],
        model_settings=_MODEL_SETTINGS,
        retries=_TOOL_RETRIES,
    )
    for fn in [list_tables, _retryable(describe_table), _retryable(execute_sql)]:
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
        capabilities=[CodeMode(max_retries=_CODE_MODE_MAX_RETRIES), MCP(mcp, native=False)],
        model_settings=_MODEL_SETTINGS,
        retries=_TOOL_RETRIES,
    )


def _build_enterprise_react_toolsearch_agent():
    """ReAct + ToolSearch: same 17 tools, but hidden behind on-demand discovery
    (`defer_loading=True`) instead of all 17 schemas being sent to the model every turn."""
    from pydantic_ai import Agent
    from pydantic_ai.capabilities import ToolSearch

    agent = Agent(
        _model(),
        system_prompt=ENTERPRISE_SYSTEM_PROMPT,
        capabilities=[ToolSearch()],
        model_settings=_MODEL_SETTINGS,
        retries=_TOOL_RETRIES,
    )
    for fn in _enterprise_tools():
        agent.tool_plain(fn, defer_loading=True)
    return agent


def _build_enterprise_codemode_toolsearch_agent():
    """Harness/CodeMode + ToolSearch: tools stay hidden until discovered, then whatever
    gets discovered is batched inside the sandboxed run_code call like plain CodeMode."""
    from pydantic_ai import Agent
    from pydantic_ai.capabilities import ToolSearch
    from pydantic_ai_harness import CodeMode

    agent = Agent(
        _model(),
        system_prompt=ENTERPRISE_SYSTEM_PROMPT,
        capabilities=[CodeMode(max_retries=_CODE_MODE_MAX_RETRIES), ToolSearch()],
        model_settings=_MODEL_SETTINGS,
        retries=_TOOL_RETRIES,
    )
    for fn in _enterprise_tools():
        agent.tool_plain(fn, defer_loading=True)
    return agent


def _enterprise_mcp_public_url() -> str:
    if not settings.enterprise_mcp_public_url:
        raise RuntimeError(
            "enterprise-mcp-react-native requires ENTERPRISE_MCP_PUBLIC_URL to be set. "
            "Native MCP tool calls are made server-side by the model provider (Anthropic / "
            "OpenAI / xAI) -- localhost is not reachable from their servers. Run "
            "`uv run python -m agent_harness.mcp_server` with a streamable-HTTP transport "
            "behind a public tunnel (e.g. ngrok) and point ENTERPRISE_MCP_PUBLIC_URL at it. "
            "See README 'MCP server' section."
        )
    return settings.enterprise_mcp_public_url


def _build_enterprise_mcp_react_native_agent():
    """ReAct via native MCP: the model provider connects to the MCP server directly instead
    of pydantic-ai proxying calls locally. Requires ENTERPRISE_MCP_PUBLIC_URL.

    No CodeMode counterpart: native MCP tool calls are executed server-side by the provider,
    never as local pydantic-ai function tools, so there is nothing CodeMode could batch into
    a sandboxed run_code call -- see `pydantic_ai_harness.CodeMode` docs (it only wraps tools
    the agent executes locally)."""
    from pydantic_ai import Agent
    from pydantic_ai.capabilities import MCP

    return Agent(
        _model(),
        system_prompt=ENTERPRISE_SYSTEM_PROMPT,
        capabilities=[MCP(_enterprise_mcp_public_url(), native=True)],
        model_settings=_MODEL_SETTINGS,
        retries=_TOOL_RETRIES,
    )


def _build_enterprise_react_thinking_agent():
    """ReAct + extended thinking: isolates whether reasoning tokens reduce wasted tool calls
    on multi-step join tasks, at the cost of latency and the temperature=0 determinism pin."""
    from pydantic_ai import Agent
    from pydantic_ai.capabilities import Thinking

    agent = Agent(
        _model(),
        system_prompt=ENTERPRISE_SYSTEM_PROMPT,
        capabilities=[Thinking()],
        model_settings=_THINKING_MODEL_SETTINGS,
        retries=_TOOL_RETRIES,
    )
    for fn in _enterprise_tools():
        agent.tool_plain(fn)
    return agent


def _build_enterprise_codemode_thinking_agent():
    """Harness/CodeMode + extended thinking: same tools batched in CodeMode, with the model
    reasoning before it writes the sandboxed run_code call."""
    from pydantic_ai import Agent
    from pydantic_ai.capabilities import Thinking
    from pydantic_ai_harness import CodeMode

    agent = Agent(
        _model(),
        system_prompt=ENTERPRISE_SYSTEM_PROMPT,
        capabilities=[CodeMode(max_retries=_CODE_MODE_MAX_RETRIES), Thinking()],
        model_settings=_THINKING_MODEL_SETTINGS,
        retries=_TOOL_RETRIES,
    )
    for fn in _enterprise_tools():
        agent.tool_plain(fn)
    return agent


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
    # ── exploratory architectures: new orchestration axes on the same 17 tools ────
    "enterprise-react-toolsearch": (
        "ReAct + ToolSearch: all 17 tools are defer_loading=True, discovered on demand "
        "instead of sent to the model up front every turn.",
        _build_enterprise_react_toolsearch_agent,
    ),
    "enterprise-codemode-toolsearch": (
        "Harness/CodeMode + ToolSearch: tools discovered on demand, then batched into "
        "the sandboxed run_code call like plain enterprise-codemode.",
        _build_enterprise_codemode_toolsearch_agent,
    ),
    "enterprise-mcp-react-native": (
        "ReAct via native MCP: the model provider calls the MCP server directly "
        "(no local proxying). Requires ENTERPRISE_MCP_PUBLIC_URL.",
        _build_enterprise_mcp_react_native_agent,
    ),
    "enterprise-react-thinking": (
        "ReAct + extended thinking: same 17 tools, model reasons before each tool call.",
        _build_enterprise_react_thinking_agent,
    ),
    "enterprise-codemode-thinking": (
        "Harness/CodeMode + extended thinking: same tools batched in CodeMode, with "
        "reasoning before the sandboxed run_code call.",
        _build_enterprise_codemode_thinking_agent,
    ),
}

# Generic CodeMode variants have no enterprise DB tools registered (`codemode` has zero
# tools at all; `codemode-mcp-search` only has HN + web search). Pairing either with an
# `adi-*`/routing-benchmark task is a structurally guaranteed failure -- the model has
# nothing usable to call inside `run_code` -- not a real architecture comparison. `minimal`
# stays available for both groups: a no-tools baseline is a deliberate contrast for
# enterprise tasks too (see README "What you can measure across them").
_GENERIC_ONLY_ARCHITECTURES = ("codemode", "codemode-mcp-search")

# Task-name prefixes that require enterprise DB access (see `agent_harness.tasks.builtins`
# and `agent_harness.tasks.routing_benchmark`): the six `adi-*` comparison tasks plus the
# seven routing-benchmark prefixes, one per enterprise architecture.
_ENTERPRISE_TASK_PREFIXES = (
    "adi-",
    "react-",
    "codemode-",
    "mcpreact-",
    "mcpcodemode-",
    "sqlreact-",
    "sqlcodemode-",
)


def architectures_for_task(task_name: str) -> list[str]:
    """Return the architecture names that can meaningfully answer a given task.

    Used by `run-all` so it doesn't pair tool-less generic CodeMode variants with
    enterprise DB tasks they can never answer (see `_GENERIC_ONLY_ARCHITECTURES`).
    """
    if task_name.startswith(_ENTERPRISE_TASK_PREFIXES):
        return [
            name for name in ARCHITECTURE_BUILDERS if name not in _GENERIC_ONLY_ARCHITECTURES
        ]
    return list(ARCHITECTURE_BUILDERS)


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
