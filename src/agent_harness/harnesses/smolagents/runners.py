"""smolagents harness: a single, tuned `CodeAgent` (https://github.com/huggingface/smolagents).

Unlike the `pydantic-ai` harness, which needs separate `enterprise-react` / `enterprise-codemode`
architectures because batching tool calls into sandboxed Python is an opt-in capability
(`CodeMode`) layered on top of a ReAct-style tool-calling `Agent`, smolagents' `CodeAgent` *is*
the code-writing loop natively — every action the model takes is a Python code blob that can
call one tool or fan out over many in a single step. So there is exactly one architecture here,
`smolagents-codeagent`, registered with the same 17-tool enterprise Decision Intelligence surface
as `enterprise-react`/`enterprise-codemode` for a direct, apples-to-apples comparison in
`reports/*/architecture_summary.csv`.

Security note: `executor_type="local"` uses smolagents' `LocalPythonExecutor`, which — like
`pydantic-ai-harness`'s Monty sandbox used by CodeMode — applies best-effort restrictions but is
NOT a security boundary. Fine for this benchmark (trusted local model, trusted tools); do not
reuse this configuration to run untrusted code. smolagents also supports `e2b`/`modal`/`docker`/
`blaxel` sandboxed executors for production use — see the smolagents README.
"""

from __future__ import annotations

import re
import time
from collections.abc import Callable
from typing import Any

from agent_harness.config import settings
from agent_harness.runners.base import AgentRunner, RunResult

# Same persona and benchmark-formatting rules as `pydantic_ai.runners.ENTERPRISE_SYSTEM_PROMPT` +
# `BENCHMARK_RESPONSE_INSTRUCTIONS`, reworded for a code-writing agent (batches calls into one
# Python snippet instead of one tool call per turn, and must explicitly call `final_answer(...)`).
SYSTEM_INSTRUCTIONS = (
    "You are an AI Decision Intelligence analyst for an enterprise platform. Your role is to "
    "connect siloed data across business functions — finance, supply chain, sales, R&D, HR, and "
    "operations — to deliver instant, actionable insights and recommendations. Use the available "
    "tools to answer questions about performance metrics, forecasts, resource allocation, and "
    "cross-functional KPIs.\n\n"
    "You write Python code to call these tools. When a task requires looking up more than one "
    "entity (e.g. several customers, orders, or modules), write a loop or list comprehension that "
    "calls the tool for every entity in ONE code block instead of issuing one call per step — that "
    "is the entire advantage of writing actions as code instead of one-tool-call-per-turn. Use "
    "`print(...)` to inspect intermediate results across steps; the sandbox keeps variables alive "
    "between code blocks.\n\n"
    "Benchmark response requirements:\n"
    "- Use the available database tools for enterprise data questions; never invent data.\n"
    "- Return only the fields requested by the user, preferably as a compact table.\n"
    "- Do not include a rank column, key insights, totals, percentages, per-seat values, dates, "
    "or any other numeric claims unless the user explicitly asks for them.\n"
    "- Do not restate numeric values from the question, such as lookback windows or requested "
    "row counts, in headings or preambles.\n"
    "- If a tool returns exactly the requested rows and fields, copy those values verbatim, in "
    "the same order, exactly once each — do not recompute, relabel, re-sort, re-aggregate, or "
    "duplicate any row.\n\n"
    'When you have the final answer, call `final_answer("...")` with the complete, formatted '
    "answer text as a string — the task is not finished until you call `final_answer`."
)

# Bounds how many ReAct/CodeAct steps (each a full model round-trip) a single run may take
# before giving up. Some `adi-*` tasks require multiple dependent lookups (e.g. per-business-
# function fan-out followed by a join); smolagents' own framework default (20) is already
# generous, but local/smaller models sometimes need an extra step or two to self-correct a bad
# code block — 24 gives a little headroom without letting a stuck run spin forever.
_MAX_STEPS = 24


def _model():
    """Return the configured smolagents model (local server or cloud via LiteLLM)."""
    return settings.build_smolagents_model()


def _enterprise_tools() -> list[Any]:
    """Wrap the same 17 typed enterprise Decision Intelligence tool functions used by the
    `pydantic-ai` harness's `enterprise-react`/`enterprise-codemode` architectures as smolagents
    `Tool` instances via the `@tool`-equivalent `tool()` factory.

    `tool()` derives each tool's JSON schema from the function's type hints and its docstring's
    `Args:` section, so this reuses `agent_harness.tools.enterprise`/`sql` completely unmodified
    (aside from small docstring additions — see `tools/enterprise.py` — needed to give every
    parameter an `Args:` description, which `tool()` requires but plain pydantic-ai tool
    registration does not).
    """
    from smolagents import tool

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
        tool(fn)
        for fn in (
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
        )
    ]


def _build_codeagent():
    """Build the tuned `CodeAgent` — this harness's one and only architecture.

    Tuning choices, all aimed at "best CodeAgent smolagents can build" for this benchmark:
      - `additional_authorized_imports` covers `json` (formatting/parsing tool output) on top of
        smolagents' generous `BASE_BUILTIN_MODULES` default, which already includes `statistics`,
        `math`, `itertools`, `collections`, `datetime`, and `re` — everything the harder
        `sqlcodemode-*`-style analytical tasks need for client-side aggregation.
      - `max_steps=24` (see module docstring) gives multi-step join tasks headroom without
        letting a stuck run spin forever.
      - `return_full_result=True` so `.run()` returns a `RunResult` with `.steps`, which
        `_extract_tool_calls` below parses for tool-selection metadata.
      - `verbosity_level=LogLevel.ERROR` keeps smolagents' own Rich console output out of
        benchmark runs (the CLI does its own result printing).
    """
    from smolagents import CodeAgent, LogLevel

    return CodeAgent(
        tools=_enterprise_tools(),
        model=_model(),
        instructions=SYSTEM_INSTRUCTIONS,
        max_steps=_MAX_STEPS,
        additional_authorized_imports=["json"],
        executor_type="local",
        verbosity_level=LogLevel.ERROR,
        return_full_result=True,
    )


ARCHITECTURE_BUILDERS: dict[str, tuple[str, Callable[[], object]]] = {
    "smolagents-codeagent": (
        "smolagents CodeAgent: 17 typed enterprise tools, actions written as Python code blobs "
        "that can batch multiple tool calls per step (no separate ReAct/CodeMode split needed).",
        _build_codeagent,
    ),
}


def architectures_for_task(_task_name: str) -> list[str]:
    """Every task is answerable: the CodeAgent always has the full 17-tool surface available
    (unused tools are simply not called for tool-less tasks like `hello` or `minimal-*`)."""
    return list(ARCHITECTURE_BUILDERS)


_TOOL_CALL_RE_CACHE: dict[tuple[str, ...], re.Pattern[str]] = {}


def _tool_call_pattern(tool_names: tuple[str, ...]) -> re.Pattern[str]:
    pattern = _TOOL_CALL_RE_CACHE.get(tool_names)
    if pattern is None:
        alternation = "|".join(re.escape(name) for name in tool_names)
        pattern = re.compile(rf"\b({alternation})\s*\(")
        _TOOL_CALL_RE_CACHE[tool_names] = pattern
    return pattern


def _extract_tool_calls(run_result: Any, tool_names: list[str]) -> list[dict[str, Any]]:
    """Best-effort, framework-agnostic list of real tool calls made during a `CodeAgent` run.

    `CodeAgent`'s own `ActionStep.tool_calls` only ever records a single synthetic
    `python_interpreter` call per step (the whole code blob) -- the real tool names live inside
    that generated code, not as discrete tool-call entries. This mirrors what
    `pydantic_ai.harnesses.traced_agent._extract_run_artifacts` does for CodeMode's nested calls:
    scan each step's generated code text for `tool_name(` occurrences among the tools actually
    registered on the agent, tagged `via="code"`. Best-effort only (a call inside a string
    literal or comment would false-positive) -- good enough for the `tool_selection_benchmark`
    recall/precision/fabrication signals, not a substitute for real execution tracing.

    `RunResult.steps` is documented as `list[dict]` (a JSON-friendly serialization of
    `agent.memory.steps`, not the live `ActionStep`/`TaskStep` objects) -- only step dicts that
    came from an `ActionStep` carry a `code_action` key at all.
    """
    if not tool_names:
        return []
    pattern = _tool_call_pattern(tuple(tool_names))
    calls: list[dict[str, Any]] = []
    steps = getattr(run_result, "steps", None) or []
    for step in steps:
        if not isinstance(step, dict):
            continue
        code = step.get("code_action")
        if not code:
            continue
        for match in pattern.finditer(code):
            calls.append({"tool_name": match.group(1), "via": "code"})
    return calls


class SmolagentsRunner(AgentRunner):
    harness_name = "smolagents"
    architecture_name: str

    def __init__(self, architecture: str) -> None:
        if architecture not in ARCHITECTURE_BUILDERS:
            raise KeyError(f"Unknown smolagents architecture: {architecture}")
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
            agent = self._build_agent()
            run_result = agent.run(prompt, reset=True)
            output = run_result.output if hasattr(run_result, "output") else run_result
            result.output = "" if output is None else str(output)

            # Exclude "final_answer": it's the agent's completion signal, always called exactly
            # once per successful run, not a real data-tool selection choice -- counting it would
            # misclassify every single run as having made a "fabricated" call (it isn't one of
            # the 17 enterprise tools `tool_selection_benchmark.py` knows about).
            tool_names = [name for name in (agent.tools or {}) if name != "final_answer"]
            result.metadata["tool_calls"] = _extract_tool_calls(run_result, tool_names)
            steps = getattr(run_result, "steps", None) or []
            result.metadata["step_count"] = sum(
                1 for s in steps if isinstance(s, dict) and "code_action" in s
            )
            token_usage = getattr(run_result, "token_usage", None)
            if token_usage is not None:
                result.metadata["token_usage"] = {
                    "input_tokens": getattr(token_usage, "input_tokens", None),
                    "output_tokens": getattr(token_usage, "output_tokens", None),
                }
        except Exception as exc:  # noqa: BLE001 — surface harness errors in bench output
            result.error = f"{type(exc).__name__}: {exc}"
        result.elapsed_seconds = time.perf_counter() - started
        return result


def make_runner(architecture: str) -> SmolagentsRunner:
    return SmolagentsRunner(architecture)
