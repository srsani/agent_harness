"""Hierarchical/categorized tool search — an architecture purpose-built for large tool counts.

Every other architecture in `runners.py` picks one point on a fixed axis: send every tool's
full schema every turn (`enterprise-react-120`), batch them behind one sandboxed `run_code`
call (`enterprise-codemode-120`), or flatten discovery into a single `search_tools` call over
the whole 120-tool corpus (`enterprise-react-toolsearch-120`). This module adds a second
discovery *level* on top of that last idea, closer to how a human would navigate a large API
reference: first find the right section, then the right function within it.

Exactly three meta-tools are ever registered on the agent, regardless of how many real tools
exist behind them — the model's per-turn context cost is flat as the tool count grows, unlike
`enterprise-react-120` where it scales linearly with the corpus size:

  1. `list_tool_categories()`             — see the ~11 business-domain categories and how
                                             many tools live in each.
  2. `search_tools_in_category(category)` — within one chosen category, see every matching
                                             tool's name, description, and parameters.
  3. `call_tool(tool_name, arguments)`    — actually invoke a tool discovered in step 2.

Categories group tools by the business domain they claim to be about (catalog, customers,
orders/sales, support, marketing, procurement, workforce, finance, external actions, general
analytics), not by "real vs. distractor" — a category has to be navigated by domain the same
way a real API reference would be, decoys included, or this would trivially defeat the point
of the distractor tools in `tools/distractors.py`.
"""

from __future__ import annotations

import inspect
import re
from collections import Counter
from typing import Any, Callable

# ── category assignment ───────────────────────────────────────────────────────────────────
# Every one of the 120 tool names from `runners._enterprise_tools_120()` is assigned to
# exactly one category below. Distractors are placed in whichever category their *name*
# plausibly belongs to (mirroring how a real internal tool catalog would be organized),
# not singled out into their own "decoys" bucket.

CATEGORY_DESCRIPTIONS: dict[str, str] = {
    "schema": "Database schema exploration and raw SQL access.",
    "catalog": "Analytics module / product catalog: search, details, ratings, adoption, top-sellers.",
    "customers": "Business user (customer) profiles, search, subscription history, lifetime value.",
    "orders_sales": "Subscription orders, sales summaries, and revenue reporting.",
    "support": "Customer support tickets, agents, resolution and satisfaction metrics.",
    "marketing": "Marketing campaigns, channel performance, ROI, and funnel metrics.",
    "procurement": "Suppliers and purchase orders: performance, risk, and spend.",
    "workforce": "Departments, employees, headcount, attrition, and performance reviews.",
    "finance": "Department budgets, expenses, variance, and capex reporting.",
    "external_actions": "Outbound actions: email, calendar, messaging, travel, document generation.",
    "analytics_general": "Cross-cutting scores and predictions (risk, health, sentiment, churn, benchmarks).",
}

_CATEGORY_TOOL_NAMES: dict[str, tuple[str, ...]] = {
    "schema": (
        "get_schema_context", "list_tables", "describe_table", "execute_sql",
    ),
    "catalog": (
        "list_categories", "search_products", "get_product", "get_product_reviews",
        "get_top_selling_products", "get_low_stock_products",
        "get_product_legacy", "list_products_old", "get_top_products_cached",
        "get_module_rating_summary", "get_low_adoption_report", "get_product_by_title",
    ),
    "customers": (
        "get_customer", "search_customers", "get_customer_orders", "get_customer_lifetime_value",
        "get_customer_v2", "get_customer_orders_summary", "get_customer_engagement_score",
        "predict_churn", "get_order_by_customer_name", "get_user_permissions",
    ),
    "orders_sales": (
        "get_order", "get_sales_summary", "get_revenue_by_month",
        "search_orders_deprecated", "get_sales_report_v1", "get_customer_orders_v1",
        "get_revenue_summary_legacy", "get_revenue_forecast", "get_top_selling_products_by_region",
    ),
    "support": (
        "list_support_agents", "get_support_agent", "search_support_tickets", "get_support_ticket",
        "get_customer_support_history", "get_ticket_resolution_stats", "get_agent_performance",
        "get_open_tickets_by_priority", "get_csat_summary",
        "get_ticket_summary", "get_ticket_by_email",
    ),
    "marketing": (
        "list_campaigns", "get_campaign", "search_campaigns", "get_campaign_performance",
        "get_campaign_roi", "get_top_campaigns_by_conversion", "get_channel_spend_breakdown",
        "get_lead_conversion_funnel", "get_monthly_marketing_spend",
        "get_campaign_summary", "get_campaign_by_name", "get_quarterly_growth_rate",
    ),
    "procurement": (
        "list_suppliers", "get_supplier", "search_suppliers", "get_purchase_order",
        "get_supplier_purchase_history", "get_supplier_performance", "get_late_delivery_report",
        "get_procurement_spend_summary", "get_supplier_risk_score",
        "get_supplier_info", "get_supplier_scorecard", "get_supplier_by_company",
        "get_purchase_order_status",
    ),
    "workforce": (
        "list_departments", "get_department", "get_employee", "search_employees",
        "get_department_headcount", "get_attrition_rate", "get_performance_review_summary",
        "get_compensation_band", "get_open_positions",
        "get_employee_record", "get_employee_directory", "get_employee_by_name",
        "get_department_by_label",
    ),
    "finance": (
        "list_budgets", "get_budget", "search_expenses", "get_expense", "get_budget_variance",
        "get_department_spend", "get_capex_summary", "get_expense_category_breakdown",
        "get_forecast_vs_actual",
        "get_budget_summary", "get_budget_by_department_name", "get_expense_by_description",
    ),
    "external_actions": (
        "send_email_notification", "create_calendar_invite", "schedule_meeting",
        "get_weather_forecast", "translate_text", "generate_pdf_report", "post_to_slack",
        "create_jira_ticket", "send_sms_alert", "book_travel",
    ),
    "analytics_general": (
        "get_ai_recommendation", "get_risk_score", "get_health_score", "get_nps_score",
        "get_market_benchmark", "get_industry_average", "get_competitor_analysis",
        "get_sentiment_score", "get_anomaly_report", "get_data_quality_score", "get_audit_log",
        "get_system_status", "get_api_usage", "get_review_by_customer_and_product",
    ),
}

CATEGORY_FOR_TOOL: dict[str, str] = {
    name: category for category, names in _CATEGORY_TOOL_NAMES.items() for name in names
}

_TOKEN_RE = re.compile(r"[a-z0-9]+")


def _tokenize(text: str) -> set[str]:
    return set(_TOKEN_RE.findall(text.lower()))


def _first_line(doc: str | None) -> str:
    return (doc or "").strip().split("\n")[0].strip()


def _param_signature(fn: Callable[..., Any]) -> list[dict[str, Any]]:
    params = []
    for name, param in inspect.signature(fn).parameters.items():
        annotation = param.annotation
        type_name = getattr(annotation, "__name__", str(annotation)) if annotation is not inspect.Parameter.empty else "Any"
        entry: dict[str, Any] = {"name": name, "type": type_name}
        if param.default is not inspect.Parameter.empty:
            entry["default"] = param.default
        params.append(entry)
    return params


def build_categorized_search_tools(
    tool_fns: list[Callable[..., Any]],
) -> list[Callable[..., Any]]:
    """Build the 3 meta-tools (list categories / search within category / call) over `tool_fns`.

    Returns plain functions meant to be registered with `agent.tool_plain(...)` — no custom
    `AbstractToolset` subclass needed; the "hierarchical discovery" behavior lives entirely in
    how these three functions are implemented, not in framework-level tool visibility plumbing.
    """
    registry: dict[str, Callable[..., Any]] = {fn.__name__: fn for fn in tool_fns}
    uncategorized = sorted(set(registry) - set(CATEGORY_FOR_TOOL))
    if uncategorized:
        raise ValueError(f"Tools missing from CATEGORY_FOR_TOOL: {uncategorized}")

    def list_tool_categories() -> list[dict[str, Any]]:
        """List every tool category with a short description and how many tools it contains.

        Always call this first. Then call `search_tools_in_category` on the single most
        relevant category to see the actual tools available in it.
        """
        counts = Counter(CATEGORY_FOR_TOOL[name] for name in registry)
        return [
            {"category": category, "description": description, "tool_count": counts.get(category, 0)}
            for category, description in CATEGORY_DESCRIPTIONS.items()
            if counts.get(category, 0) > 0
        ]

    def search_tools_in_category(category: str, query: str = "") -> list[dict[str, Any]]:
        """List tools within one category, each with its name, description, and parameters.

        Args:
            category: Exact category name from `list_tool_categories` (e.g. 'customers').
            query: Optional keyword(s) to rank/filter tools within the category by relevance
                to your task. Empty returns every tool in the category.
        """
        names = [name for name in registry if CATEGORY_FOR_TOOL.get(name) == category]
        if not names:
            valid = sorted({CATEGORY_FOR_TOOL[n] for n in registry})
            return [{"error": f"Unknown category {category!r}. Valid categories: {valid}"}]

        if query.strip():
            terms = _tokenize(query)

            def score(name: str) -> int:
                fn = registry[name]
                return len(terms & _tokenize(f"{name} {fn.__doc__ or ''}"))

            scored = [(score(name), name) for name in names]
            matched = [name for s, name in scored if s > 0]
            names = matched if matched else names
            names.sort(key=score, reverse=True)

        return [
            {
                "tool_name": name,
                "description": _first_line(registry[name].__doc__),
                "parameters": _param_signature(registry[name]),
            }
            for name in names
        ]

    def call_tool(tool_name: str, arguments: dict[str, Any] | None = None) -> Any:
        """Invoke a tool by name, previously discovered via `search_tools_in_category`.

        Args:
            tool_name: Exact tool name as returned by `search_tools_in_category`.
            arguments: Keyword arguments for the tool, as a JSON object. Omit or pass {} for
                a tool that takes no arguments.
        """
        from pydantic_ai import ModelRetry

        fn = registry.get(tool_name)
        if fn is None:
            raise ModelRetry(
                f"Unknown tool_name {tool_name!r}. Call list_tool_categories and "
                "search_tools_in_category first to find a valid tool name."
            )
        try:
            return fn(**(arguments or {}))
        except TypeError as exc:
            raise ModelRetry(f"Invalid arguments for {tool_name!r}: {exc}") from exc
        except ModelRetry:
            raise
        except Exception as exc:  # noqa: BLE001 -- surface any tool-raised error as a retry
            raise ModelRetry(str(exc)) from exc

    return [list_tool_categories, search_tools_in_category, call_tool]
