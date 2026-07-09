"""Tool-selection accuracy & tool-hallucination benchmark for the 120-tool scale test.

This module answers a third question, distinct from both `tasks/builtins.py` +
`scripts/generate_ground_truth.py` ("is the final answer correct?") and
`tasks/routing_benchmark.py` ("which architecture is the best structural fit?"):
*"did the agent call the right tool(s), and did it avoid calling wrong/distractor/fabricated
tools while doing it?"*

This is the primary instrument for the "120 tools" half of the harness-selection question:
as the tool surface grows from 17 (core) to 120 (core + 45 new real + 58 distractors), does
tool-selection precision hold up, and does the agent ever call a plausible-sounding tool that
is actively wrong (`DISTRACTOR_TOOLS`) or that doesn't exist in the registry at all (a
genuinely fabricated/hallucinated tool call)?

Design
------
Every task in `TASKS` (see `tasks/builtins.py`) maps to a `TOOL_SELECTION_BENCHMARK` entry
with:

  - `expected_tools`  — the tool name(s) that correctly answer this task. For single-call
                         tasks this is exactly one name. For fan-out (CodeMode) or multi-stage
                         tasks it lists every tool that legitimately participates; recall is
                         satisfied if *any* of them appears in the trace (an OR, not an AND —
                         several of these tasks have more than one valid decomposition, e.g.
                         a raw SQL query vs. a chain of typed tool calls).
  - `notes`           — (optional) caveat when the mapping is best-effort rather than exact.

Two families of tasks are intentionally out of scope and excluded from `TOOL_SELECTION_BENCHMARK`:
`hn-research` (legitimately calls an external HN/web tool outside the enterprise tool universe)
and the `minimal-greeting-*`/`minimal-faq-capabilities` conversational tasks (correctly answered
with zero tool calls, same as every other `minimal-*` task, so they're covered by the blanket
`expected_tools: []` rule below rather than needing individual entries).

The 50 new `support-*`/`marketing-*`/`procurement-*`/`workforce-*`/`finance-*` tasks (added
specifically for this benchmark) have exact 1:1 `expected_tools` mappings because their ground
truth in `generate_ground_truth.py` is computed by calling that exact tool function. The 100
pre-existing tasks (`adi-*`, `react-*`, `codemode-*`, `mcpreact-*`, `mcpcodemode-*`,
`sqlreact-*`, `sqlcodemode-*`, `minimal-*`) have best-effort mappings based on which of the 17
core tools' documented shape matches the task, using `routing_benchmark.py` as a cross-check
for the single-call families.

`forbidden_tools` is NOT stored per-task: it is always the full `DISTRACTOR_TOOLS` registry
(imported from `tools/distractors.py`) because none of the 58 distractor tools is ever the
right choice for *any* task in this benchmark, independent of what's being asked. See
`score_tool_selection` for how this and `expected_tools` combine into precision/recall/
hallucination metrics.
"""

from __future__ import annotations

from typing import Any

from agent_harness.tasks.builtins import TASKS
from agent_harness.tools.distractors import DISTRACTOR_TOOLS

# ═══════════════════════════════════════════════════════════════════════════
# Tool universe
# ═══════════════════════════════════════════════════════════════════════════

CORE_TOOLS: frozenset[str] = frozenset(
    {
        "get_schema_context",
        "list_categories",
        "search_products",
        "get_product",
        "get_product_reviews",
        "get_top_selling_products",
        "get_low_stock_products",
        "get_customer",
        "search_customers",
        "get_customer_orders",
        "get_customer_lifetime_value",
        "get_order",
        "get_sales_summary",
        "get_revenue_by_month",
        "list_tables",
        "describe_table",
        "execute_sql",
    }
)

NEW_DOMAIN_TOOLS: frozenset[str] = frozenset(
    {
        # support
        "list_support_agents",
        "get_support_agent",
        "search_support_tickets",
        "get_support_ticket",
        "get_customer_support_history",
        "get_ticket_resolution_stats",
        "get_agent_performance",
        "get_open_tickets_by_priority",
        "get_csat_summary",
        # marketing
        "list_campaigns",
        "get_campaign",
        "search_campaigns",
        "get_campaign_performance",
        "get_campaign_roi",
        "get_top_campaigns_by_conversion",
        "get_channel_spend_breakdown",
        "get_lead_conversion_funnel",
        "get_monthly_marketing_spend",
        # procurement
        "list_suppliers",
        "get_supplier",
        "search_suppliers",
        "get_purchase_order",
        "get_supplier_purchase_history",
        "get_supplier_performance",
        "get_late_delivery_report",
        "get_procurement_spend_summary",
        "get_supplier_risk_score",
        # workforce
        "list_departments",
        "get_department",
        "get_employee",
        "search_employees",
        "get_department_headcount",
        "get_attrition_rate",
        "get_performance_review_summary",
        "get_compensation_band",
        "get_open_positions",
        # finance
        "list_budgets",
        "get_budget",
        "search_expenses",
        "get_expense",
        "get_budget_variance",
        "get_department_spend",
        "get_capex_summary",
        "get_expense_category_breakdown",
        "get_forecast_vs_actual",
    }
)

assert len(CORE_TOOLS) == 17, f"expected 17 core tools, got {len(CORE_TOOLS)}"
assert len(NEW_DOMAIN_TOOLS) == 45, f"expected 45 new real tools, got {len(NEW_DOMAIN_TOOLS)}"
assert len(DISTRACTOR_TOOLS) == 58, f"expected 58 distractor tools, got {len(DISTRACTOR_TOOLS)}"

# Every legitimately callable tool at the 120-tool scale. A call to a name outside this set is
# not a "wrong choice" (that's what DISTRACTOR_TOOLS is for) but a genuinely fabricated /
# invented tool call -- the model asserting a tool exists that was never registered at all.
ALL_VALID_TOOLS: frozenset[str] = CORE_TOOLS | NEW_DOMAIN_TOOLS | DISTRACTOR_TOOLS
assert len(ALL_VALID_TOOLS) == 120, f"expected 120 total tools, got {len(ALL_VALID_TOOLS)}"

# Schema/table-discovery calls are never a mis-selection, regardless of which task they're
# made for -- they're how a model is supposed to behave when unsure of the schema.
SQL_DISCOVERY_TOOLS: frozenset[str] = frozenset({"list_tables", "describe_table", "get_schema_context"})

# Meta-tools that exist only because of *how* an architecture discovers/dispatches real tools,
# not because the model invented them: pydantic-ai's built-in `ToolSearch` capability exposes
# `search_tools` (see `_build_enterprise_react_toolsearch_120_agent`); the categorized-search
# architecture exposes `list_tool_categories` and `search_tools_in_category` for discovery, and
# `call_tool` as its dispatch tool (see `categorized_search.py`). None of these are in
# `ALL_VALID_TOOLS` (they aren't one of the 120 domain/distractor tools) and none of them is a
# fabricated/hallucinated tool call -- they're the harness's own discovery/dispatch mechanism,
# so they're treated the same as `SQL_DISCOVERY_TOOLS`: never a mis-selection, never counted as
# fabricated. `call_tool`'s dispatched target is additionally unpacked into its own call entry
# by `runners.py`'s `_tool_call_names` and scored normally (as if it were a native call).
ARCHITECTURE_META_TOOLS: frozenset[str] = frozenset(
    {"search_tools", "list_tool_categories", "search_tools_in_category", "call_tool"}
)


def _normalize_tool_name(name: str) -> str:
    """Undo pydantic-ai's `MCP(..., native=False)` capability tool-name namespacing.

    The `enterprise-mcp-react`/`enterprise-mcp-codemode`/`enterprise-mcp-react-120`
    architectures proxy every FastMCP-served tool locally and pydantic-ai renames each one
    with a `tool_` prefix (e.g. `get_customer` -> `tool_get_customer`) to keep MCP-served
    tools namespaced from natively-registered ones. Without undoing this, every single MCP
    architecture call looks "fabricated" even when it's calling a perfectly valid, correctly
    chosen tool -- comparing against a bare-name-stripped variant when the prefixed form isn't
    itself a known name keeps the scoring architecture-transport-agnostic.
    """
    if name not in ALL_VALID_TOOLS and name not in ARCHITECTURE_META_TOOLS and name.startswith("tool_"):
        stripped = name[len("tool_") :]
        if stripped in ALL_VALID_TOOLS or stripped in ARCHITECTURE_META_TOOLS:
            return stripped
    return name


def _entry(*expected_tools: str, notes: str = "") -> dict[str, Any]:
    d: dict[str, Any] = {"expected_tools": list(expected_tools)}
    if notes:
        d["notes"] = notes
    return d


# ═══════════════════════════════════════════════════════════════════════════
# adi-* — original enterprise benchmark (multi-tool / ambiguous decomposition)
# ═══════════════════════════════════════════════════════════════════════════

_ADI = {
    "adi-top-modules": _entry("get_top_selling_products"),
    "adi-low-adoption": _entry("get_low_stock_products"),
    "adi-user-lookup": _entry(
        "get_customer",
        "get_customer_orders",
        "execute_sql",
        notes="Answerable via get_customer + get_customer_orders, or a single joined SQL query.",
    ),
    "adi-function-analysis": _entry(
        "execute_sql",
        notes="Per-category 6-month revenue + top-module-per-category has no matching typed "
        "tool combination; a raw SQL query is the natural path.",
    ),
    "adi-function-opportunity": _entry(
        "execute_sql",
        notes="Combines revenue, ratings, and low-adoption counts per category -- no typed "
        "tool covers this shape.",
    ),
    "adi-executive-users": _entry(
        "execute_sql",
        "search_customers",
        "get_customer_lifetime_value",
        notes="Gold-tier LTV ranking + city breakdown: doable via SQL, or search_customers "
        "fanned out into get_customer_lifetime_value per user.",
    ),
    "adi-module-ratings": _entry(
        "execute_sql",
        "get_product_reviews",
        notes="Highest/lowest-rated modules with a sample review title needs a ratings "
        "aggregate no single typed tool exposes.",
    ),
    "adi-monthly-trend": _entry("get_revenue_by_month"),
    "adi-disengagement-risk": _entry(
        "execute_sql", notes="Multi-attribute cohort filter (subscription count + recency)."
    ),
    "adi-portfolio-depth": _entry(
        "execute_sql", notes="Avg modules-per-subscription and avg value by tier is a custom aggregate."
    ),
}

# ═══════════════════════════════════════════════════════════════════════════
# react-* / mcpreact-* — single-call, direct 1:1 typed-tool match
# ═══════════════════════════════════════════════════════════════════════════

_REACT = {
    "react-customer-profile-77": _entry("get_customer"),
    "react-product-detail-15": _entry("get_product"),
    "react-low-adoption-threshold-20": _entry("get_low_stock_products"),
    "react-top-modules-30days": _entry("get_top_selling_products"),
    "react-recent-reviews-module-8": _entry("get_product_reviews"),
    "react-sales-summary-60d": _entry("get_sales_summary"),
    "react-category-catalogue": _entry("list_categories"),
    "react-search-products-supplychain": _entry("search_products"),
    "react-search-customers-gold-london": _entry("search_customers"),
    "react-customer-orders-history-130": _entry("get_customer_orders"),
    "react-order-detail-500": _entry("get_order"),
    "react-customer-lifetime-value-17": _entry("get_customer_lifetime_value"),
}

_MCPREACT = {
    "mcpreact-customer-profile-155": _entry("get_customer"),
    "mcpreact-product-detail-40": _entry("get_product"),
    "mcpreact-low-adoption-threshold-15": _entry("get_low_stock_products"),
    "mcpreact-top-modules-45days": _entry("get_top_selling_products"),
    "mcpreact-recent-reviews-module-60": _entry("get_product_reviews"),
    "mcpreact-sales-summary-30d": _entry("get_sales_summary"),
    "mcpreact-search-products-finance": _entry("search_products"),
    "mcpreact-search-customers-silver-berlin": _entry("search_customers"),
    "mcpreact-customer-orders-history-180": _entry("get_customer_orders"),
    "mcpreact-order-detail-900": _entry("get_order"),
    "mcpreact-customer-lifetime-value-110": _entry("get_customer_lifetime_value"),
    "mcpreact-revenue-by-month-lastyear": _entry("get_revenue_by_month"),
}

# ═══════════════════════════════════════════════════════════════════════════
# codemode-* / mcpcodemode-* — fan-out loops (may legitimately use 1-3 tools)
# ═══════════════════════════════════════════════════════════════════════════

_CODEMODE = {
    "codemode-gold-lifetime-scan": _entry("search_customers", "get_customer", "execute_sql"),
    "codemode-customer-batch-lookup": _entry("get_customer"),
    "codemode-module-review-gap-scan": _entry("get_product_reviews", "get_product"),
    "codemode-order-batch-audit": _entry("get_order"),
    "codemode-top-module-review-quality": _entry("get_top_selling_products", "get_product_reviews"),
    "codemode-gold-churn-scan": _entry("search_customers", "get_customer_orders", "execute_sql"),
    "codemode-lowstock-unreviewed": _entry("get_low_stock_products", "get_product_reviews"),
    "codemode-category-price-spread": _entry("list_categories", "search_products"),
    "codemode-recent-multi-subscribers": _entry("get_customer_orders"),
    "codemode-bundle-scan": _entry("get_order"),
    "codemode-most-reviewed-deepdive": _entry(
        "search_products", "get_product", "get_product_reviews", "execute_sql"
    ),
    "codemode-early-cohort-value": _entry("search_customers", "get_customer", "execute_sql"),
}

_MCPCODEMODE = {
    "mcpcodemode-silver-lifetime-scan": _entry("search_customers", "get_customer", "execute_sql"),
    "mcpcodemode-customer-batch-lookup": _entry("get_customer"),
    "mcpcodemode-module-review-gap-scan-rd": _entry("search_products", "get_product_reviews"),
    "mcpcodemode-order-batch-audit": _entry("get_order"),
    "mcpcodemode-top-module-price-value": _entry("get_top_selling_products", "get_product"),
    "mcpcodemode-silver-churn-scan": _entry("search_customers", "get_customer_orders", "execute_sql"),
    "mcpcodemode-highprice-lowrating-scan": _entry("execute_sql", "get_product"),
    "mcpcodemode-category-deployment-spread": _entry("list_categories", "search_products"),
    "mcpcodemode-recent-multi-subscribers": _entry("get_customer_orders"),
    "mcpcodemode-bundle-scan": _entry("get_order"),
    "mcpcodemode-least-reviewed-deepdive": _entry(
        "search_products", "get_product", "get_product_reviews", "execute_sql"
    ),
    "mcpcodemode-recent-cohort-value": _entry("get_customer", "search_customers", "execute_sql"),
}

# ═══════════════════════════════════════════════════════════════════════════
# sqlreact-* / sqlcodemode-* — SQL-only architecture, execute_sql is the answer tool
# ═══════════════════════════════════════════════════════════════════════════

_SQLREACT_KEYS = [
    "sqlreact-module-affinity",
    "sqlreact-median-price",
    "sqlreact-revenue-per-module-efficiency",
    "sqlreact-cross-functional-power-users",
    "sqlreact-bundle-percentage",
    "sqlreact-tier-rating-gap",
    "sqlreact-fast-movers",
    "sqlreact-mom-active-users",
    "sqlreact-data-integrity-check",
    "sqlreact-city-subscription-value",
    "sqlreact-early-cohort-comparison",
    "sqlreact-rating-trend",
]
_SQLCODEMODE_KEYS = [
    "sqlcodemode-rating-distribution-top5",
    "sqlcodemode-price-rating-correlation",
    "sqlcodemode-subscription-outliers",
    "sqlcodemode-customer-spend-jump",
    "sqlcodemode-price-consistency-by-function",
    "sqlcodemode-subscription-cadence",
    "sqlcodemode-weighted-quality-score",
    "sqlcodemode-unreviewed-below-median",
    "sqlcodemode-gold-category-overlap",
    "sqlcodemode-seat-normalization-simulation",
    "sqlcodemode-revenue-momentum",
    "sqlcodemode-composite-engagement-score",
]
_SQL_ONLY = {
    key: _entry("execute_sql") for key in (_SQLREACT_KEYS + _SQLCODEMODE_KEYS)
}

# ═══════════════════════════════════════════════════════════════════════════
# minimal-* — zero tool calls expected (pure reasoning, small talk, or FAQ)
# ═══════════════════════════════════════════════════════════════════════════

_MINIMAL = {key: _entry() for key in TASKS if key.startswith("minimal-")}
_MINIMAL.update({key: _entry() for key in ("hello", "reasoning")})

# ═══════════════════════════════════════════════════════════════════════════
# 120-tool scale benchmark — the 50 new domain tasks. Primary mapping is the exact 1:1 tool
# `generate_ground_truth.py` calls for that task's ground truth; `execute_sql` is always also
# listed as acceptable because every enterprise-* architecture (17-tool, SQL-only, or 120-tool)
# has it and the new tables are reachable through it even without a purpose-built typed tool.
# ═══════════════════════════════════════════════════════════════════════════


def _scale_entry(primary_tool: str) -> dict[str, Any]:
    return _entry(
        primary_tool,
        "execute_sql",
        notes="execute_sql is an always-acceptable fallback for 17-tool/SQL-only "
        "architectures with no purpose-built tool for this new domain.",
    )


_SCALE = {
    # support
    "support-agent-profile-5": _scale_entry("get_support_agent"),
    "support-open-tickets-priority": _scale_entry("get_open_tickets_by_priority"),
    "support-ticket-detail-10": _scale_entry("get_support_ticket"),
    "support-csat-90d": _scale_entry("get_csat_summary"),
    "support-resolution-stats-180d": _scale_entry("get_ticket_resolution_stats"),
    "support-agent-performance-3": _scale_entry("get_agent_performance"),
    "support-customer-history-42": _scale_entry("get_customer_support_history"),
    "support-search-urgent-open": _scale_entry("search_support_tickets"),
    "support-list-agents": _scale_entry("list_support_agents"),
    "support-tickets-for-module-8": _scale_entry("search_support_tickets"),
    # marketing
    "marketing-list-campaigns": _scale_entry("list_campaigns"),
    "marketing-campaign-detail-5": _scale_entry("get_campaign"),
    "marketing-campaign-performance-5": _scale_entry("get_campaign_performance"),
    "marketing-campaign-roi-5": _scale_entry("get_campaign_roi"),
    "marketing-top-campaigns-conversion": _scale_entry("get_top_campaigns_by_conversion"),
    "marketing-channel-spend-365d": _scale_entry("get_channel_spend_breakdown"),
    "marketing-funnel-5": _scale_entry("get_lead_conversion_funnel"),
    "marketing-search-paid-search-active": _scale_entry("search_campaigns"),
    "marketing-monthly-spend-2025": _scale_entry("get_monthly_marketing_spend"),
    "marketing-search-webinar": _scale_entry("search_campaigns"),
    # procurement
    "procurement-list-suppliers": _scale_entry("list_suppliers"),
    "procurement-supplier-detail-10": _scale_entry("get_supplier"),
    "procurement-po-detail-50": _scale_entry("get_purchase_order"),
    "procurement-supplier-history-10": _scale_entry("get_supplier_purchase_history"),
    "procurement-supplier-performance-10": _scale_entry("get_supplier_performance"),
    "procurement-late-deliveries-365d": _scale_entry("get_late_delivery_report"),
    "procurement-spend-summary-2025": _scale_entry("get_procurement_spend_summary"),
    "procurement-supplier-risk-10": _scale_entry("get_supplier_risk_score"),
    "procurement-search-software-highrating": _scale_entry("search_suppliers"),
    "procurement-search-us-suppliers": _scale_entry("search_suppliers"),
    # workforce
    "workforce-list-departments": _scale_entry("list_departments"),
    "workforce-department-detail-3": _scale_entry("get_department"),
    "workforce-employee-detail-10": _scale_entry("get_employee"),
    "workforce-headcount-3": _scale_entry("get_department_headcount"),
    "workforce-attrition-3-365d": _scale_entry("get_attrition_rate"),
    "workforce-review-summary-10": _scale_entry("get_performance_review_summary"),
    "workforce-compensation-band-manager": _scale_entry("get_compensation_band"),
    "workforce-open-positions": _scale_entry("get_open_positions"),
    "workforce-search-finance-analysts": _scale_entry("search_employees"),
    "workforce-search-tenure-3y": _scale_entry("search_employees"),
    # finance
    "finance-list-budgets": _scale_entry("list_budgets"),
    "finance-budget-detail-10": _scale_entry("get_budget"),
    "finance-budget-variance-10": _scale_entry("get_budget_variance"),
    "finance-capex-summary-2025": _scale_entry("get_capex_summary"),
    "finance-expense-breakdown-2025": _scale_entry("get_expense_category_breakdown"),
    "finance-search-capex-expenses": _scale_entry("search_expenses"),
    "finance-department-spend-rd-2025": _scale_entry("get_department_spend"),
    "finance-forecast-vs-actual-rd-2025": _scale_entry("get_forecast_vs_actual"),
    "finance-expense-detail-10": _scale_entry("get_expense"),
    "finance-search-department-expenses-rd": _scale_entry("search_expenses"),
}

TOOL_SELECTION_BENCHMARK: dict[str, dict[str, Any]] = {
    **_ADI,
    **_REACT,
    **_MCPREACT,
    **_CODEMODE,
    **_MCPCODEMODE,
    **_SQL_ONLY,
    **_MINIMAL,
    **_SCALE,
}

for _task_key in TOOL_SELECTION_BENCHMARK:
    if _task_key not in TASKS:
        raise KeyError(f"tool_selection_benchmark references unknown task '{_task_key}'")


def score_tool_selection(task_name: str, tool_calls: list[dict[str, Any]]) -> dict[str, Any] | None:
    """Score one run's tool-call trace against the task's expected tool(s).

    `tool_calls` is `RunResult.metadata["tool_calls"]`: a flat list of
    `{"tool_name": str, "via": str}` dicts (already unpacking CodeMode's nested sandboxed
    calls and the categorized-search architecture's dispatch calls -- see `runners.py`'s
    `_tool_call_names`).

    Returns `None` if `task_name` isn't in `TOOL_SELECTION_BENCHMARK` (e.g. `hn-research`,
    which legitimately uses a tool outside this benchmark's universe).
    """
    entry = TOOL_SELECTION_BENCHMARK.get(task_name)
    if entry is None:
        return None

    expected_tools: set[str] = set(entry["expected_tools"])
    names = [_normalize_tool_name(c["tool_name"]) for c in tool_calls]
    total_calls = len(names)

    distractor_calls = [n for n in names if n in DISTRACTOR_TOOLS]
    fabricated_calls = [
        n for n in names if n not in ALL_VALID_TOOLS and n not in ARCHITECTURE_META_TOOLS
    ]
    acceptable = expected_tools | SQL_DISCOVERY_TOOLS | ARCHITECTURE_META_TOOLS
    on_target_calls = [n for n in names if n in acceptable]

    if not expected_tools:
        # A "no tool needed" task (minimal-*, hello, reasoning): recall is trivially satisfied
        # by making zero calls; any call at all (even a valid one) is unnecessary overhead,
        # and a distractor/fabricated call here is a routing failure, not just noise.
        recall = 1.0 if total_calls == 0 else 0.0
        precision = 1.0 if total_calls == 0 else (len(on_target_calls) / total_calls)
    else:
        recall = 1.0 if (expected_tools & set(names)) else 0.0
        precision = (len(on_target_calls) / total_calls) if total_calls else 0.0

    return {
        "scorable": True,
        "expected_tools": sorted(expected_tools),
        "total_tool_calls": total_calls,
        "tool_recall": round(recall, 4),
        "tool_precision": round(precision, 4),
        "distractor_call_count": len(distractor_calls),
        "distractor_calls": distractor_calls,
        "any_distractor_called": len(distractor_calls) > 0,
        "distractor_call_rate": round(len(distractor_calls) / total_calls, 4) if total_calls else 0.0,
        "fabricated_call_count": len(fabricated_calls),
        "fabricated_calls": fabricated_calls,
        "any_fabricated_called": len(fabricated_calls) > 0,
        "fabricated_call_rate": round(len(fabricated_calls) / total_calls, 4) if total_calls else 0.0,
    }
