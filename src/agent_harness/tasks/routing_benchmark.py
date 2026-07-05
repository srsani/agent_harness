"""Architecture routing benchmark for the six enterprise Decision Intelligence architectures.

This module answers a different question than `tasks/builtins.py` +
`scripts/generate_ground_truth.py`. Those two answer:
*"is the agent's numeric/textual answer correct?"* This module answers:
*"given a user request, which of the six architectures is structurally the best fit to handle it,
and why?"*

Each of the 87 tasks in `TASKS` under the `minimal-*`, `react-*`, `codemode-*`, `mcpreact-*`,
`mcpcodemode-*`, `sqlreact-*`, and `sqlcodemode-*` prefixes was written so that ONE architecture
has a genuine structural edge answering it. `ROUTING_BENCHMARK[architecture]` lists those tasks
together with:

  - `why`              — the specific reason this architecture is the best fit for this question
  - `alternatives`      — for each of the other 6 architectures, why it's a worse fit here
  - `routing_signals`   — surface features of the question a router could use to make this call
                          without running every architecture and comparing outputs

`ANALYSIS` then rolls this up into decision-boundary rules for: minimal (no tools) vs any of the
six data-tool architectures, ReAct vs CodeMode (within the typed-tool, MCP, and SQL-only tool
families), direct typed tools vs local FastMCP tools, and full enterprise tools vs SQL-only tools.

Use `ROUTING_BENCHMARK` when building/evaluating an automatic router: the target label is the
architecture choice, not the final numeric answer, so it is intentionally kept separate from the
deterministic ground truth in `scripts/generate_ground_truth.py`.
"""

from __future__ import annotations

from typing import Any

from agent_harness.tasks.builtins import TASKS

ARCHITECTURES: list[str] = [
    "minimal",
    "enterprise-react",
    "enterprise-codemode",
    "enterprise-mcp-react",
    "enterprise-mcp-codemode",
    "enterprise-sql-react",
    "enterprise-sql-codemode",
]


def _build_group(
    prefix: str,
    architecture: str,
    per_task_why: list[tuple[str, str]],
    alternatives: dict[str, str],
    routing_signals: list[str],
) -> list[dict[str, Any]]:
    """Assemble one architecture's routing entries.

    `per_task_why` is a list of (task_key, why) pairs specific to each question.
    `alternatives` and `routing_signals` are shared across the whole group because the
    structural reason the other five architectures lose doesn't change question to question —
    only the specific numbers/entities being asked about do.
    """
    entries = []
    for task_key, why in per_task_why:
        if task_key not in TASKS:
            raise KeyError(f"routing_benchmark references unknown task '{task_key}'")
        if not task_key.startswith(prefix):
            raise ValueError(f"task '{task_key}' does not match expected prefix '{prefix}-'")
        entries.append(
            {
                "task_key": task_key,
                "question": TASKS[task_key],
                "ideal_architecture": architecture,
                "why": why,
                "alternatives": dict(alternatives),
                "routing_signals": list(routing_signals),
            }
        )
    return entries


# ═══════════════════════════════════════════════════════════════════════════
# enterprise-react
# ═══════════════════════════════════════════════════════════════════════════

_REACT_ALTERNATIVES = {
    "minimal": (
        "Has no tools at all — cannot look up this customer/product/order record and can only "
        "guess or hallucinate a plausible-looking but wrong answer."
    ),
    "enterprise-codemode": (
        "Correct, but pays for a Monty sandbox spin-up and code-generation round trip with "
        "nothing to batch — pure overhead when only 1-2 calls are needed."
    ),
    "enterprise-mcp-react": (
        "Functionally identical (same tool semantics), but adds an MCP transport hop for no "
        "benefit when the tool is already available in-process."
    ),
    "enterprise-mcp-codemode": (
        "Combines both sources of unnecessary overhead: MCP transport plus an unused sandbox."
    ),
    "enterprise-sql-react": (
        "Can answer it, but the model must rediscover the schema and hand-write SQL that a "
        "tested typed tool already encapsulates correctly — more turns, more room for error."
    ),
    "enterprise-sql-codemode": (
        "Same schema-rediscovery cost as sql-react, plus sandbox overhead for a 1-2 call task."
    ),
}
_REACT_SIGNALS = [
    "Question references a single ID or a small, fixed filter (one customer, one product, one "
    "order).",
    "No words implying iteration ('each', 'every', 'for all') or a large result set to process.",
    "The exact answer shape matches an existing typed tool's return value one-to-one.",
    "Answerable in 1-2 tool calls with no cross-call aggregation needed.",
]

_REACT_WHY = [
    (
        "react-customer-profile-77",
        "Single get_customer(77) call returns every field asked for — nothing to batch.",
    ),
    (
        "react-product-detail-15",
        "One get_product(15) call already joins category + avg rating; no iteration needed.",
    ),
    (
        "react-low-adoption-threshold-20",
        "get_low_stock_products(threshold=20) is a single parameterized call.",
    ),
    (
        "react-top-modules-30days",
        "get_top_selling_products(limit=5, days=30) answers this in one call.",
    ),
    (
        "react-recent-reviews-module-8",
        "get_product_reviews(8, limit=5) is a direct one-call match.",
    ),
    (
        "react-sales-summary-60d",
        "get_sales_summary(start, end) computes all three metrics in one call.",
    ),
    (
        "react-category-catalogue",
        "list_categories() with zero arguments — the simplest possible lookup.",
    ),
    (
        "react-search-products-supplychain",
        "search_products(category=, max_price=) is a single filtered call.",
    ),
    ("react-search-customers-gold-london", "search_customers(tier=, city=) answers this directly."),
    (
        "react-customer-orders-history-130",
        "get_customer_orders(130) returns the exact list requested.",
    ),
    ("react-order-detail-500", "get_order(500) already returns header + line items together."),
    (
        "react-customer-lifetime-value-17",
        "Question is phrased to match get_customer_lifetime_value's own delivered-only "
        "definition exactly, so the typed tool is correct on the first call with no ambiguity.",
    ),
]

# ═══════════════════════════════════════════════════════════════════════════
# enterprise-codemode
# ═══════════════════════════════════════════════════════════════════════════

_CODEMODE_ALTERNATIVES = {
    "minimal": (
        "Has no tools at all — cannot enumerate or look up any of the entities this question "
        "fans out over, so it can only guess or hallucinate."
    ),
    "enterprise-react": (
        "Same typed tools, but one model round trip per entity — 10-25+ serial turns instead of "
        "one sandboxed loop, so it is far slower and more likely to be truncated or lose context."
    ),
    "enterprise-mcp-react": (
        "Same per-entity serial-turn problem as enterprise-react, plus MCP transport overhead "
        "per call."
    ),
    "enterprise-mcp-codemode": (
        "Can batch the same way, but pays an MCP transport hop for every one of the many calls "
        "inside the sandbox — real but avoidable overhead when the tools are already in-process."
    ),
    "enterprise-sql-react": (
        "Could write one aggregate SQL query instead of fanning out, but then has to re-derive "
        "the exact per-entity business logic (e.g. delivered-only lifetime value) from scratch "
        "without get_schema_context's documented formulas — higher risk of a subtly wrong metric."
    ),
    "enterprise-sql-codemode": (
        "Same SQL re-derivation risk as sql-react; also lacks the typed tool's guaranteed-correct "
        "per-entity computation that CodeMode can just call in a loop."
    ),
}
_CODEMODE_SIGNALS = [
    "Question enumerates a list of entities or implies 'every'/'each' over a double-digit "
    "population.",
    "A per-entity typed-tool call (not a single GROUP BY) is the natural way to answer.",
    "Two dependent stages are implied: discover a list, then look up details for each item in it.",
    "Answering via ReAct would need noticeably more than 3-4 sequential tool calls.",
]

_CODEMODE_WHY = [
    (
        "codemode-gold-lifetime-scan",
        "Requires scanning every gold-tier customer (dozens) and ranking by a computed value — "
        "a loop over get_customer-style calls batched in one sandbox run beats one turn per "
        "customer.",
    ),
    (
        "codemode-customer-batch-lookup",
        "20 explicit customer IDs to look up and filter — a textbook fan-out loop.",
    ),
    (
        "codemode-module-review-gap-scan",
        "24 explicit product IDs each need a reviews check — batched loop vs. 24 ReAct turns.",
    ),
    (
        "codemode-order-batch-audit",
        "20 orders must each be fetched and their line items combined — one sandboxed loop plus "
        "in-script aggregation replaces 20 round trips.",
    ),
    (
        "codemode-top-module-review-quality",
        "Chained fan-out: first discover the top 10 modules, then call the reviews tool 10 more "
        "times — naturally expressed as one dependent loop in code.",
    ),
    (
        "codemode-gold-churn-scan",
        "Every gold customer (dozens) needs an order-recency check — same batched-scan pattern.",
    ),
    (
        "codemode-lowstock-unreviewed",
        "Unknown-size list of low-stock modules, each needing an independent reviews lookup.",
    ),
    (
        "codemode-category-price-spread",
        "5 dependent search_products calls (one per business function) with client-side "
        "min/max/avg — cheap to batch, wasteful as 5 separate ReAct turns plus manual "
        "arithmetic.",
    ),
    (
        "codemode-recent-multi-subscribers",
        "21 customers each need an order-history pull and a recency filter — fan-out over a range.",
    ),
    (
        "codemode-bundle-scan",
        "20 orders each need their line items expanded and counted — loop-and-filter is the "
        "natural implementation.",
    ),
    (
        "codemode-most-reviewed-deepdive",
        "Chained fan-out: rank all modules by review count, then pull the most recent review "
        "title for the top 10 — a dependent second-stage loop.",
    ),
    (
        "codemode-early-cohort-value",
        "Unknown-size early-cohort of customers, each needing a lifetime-value computation.",
    ),
]

# ═══════════════════════════════════════════════════════════════════════════
# enterprise-mcp-react
# ═══════════════════════════════════════════════════════════════════════════

_MCPREACT_ALTERNATIVES = {
    "minimal": (
        "Has no tools at all — cannot reach this data through any channel, MCP or otherwise, "
        "and can only guess or hallucinate."
    ),
    "enterprise-react": (
        "Would return the identical answer (same underlying tool logic) with slightly lower "
        "latency — the only reason to prefer MCP here is deployment context, e.g. the tool "
        "server is centrally hosted/shared or must be independently auditable per call, which "
        "direct in-process registration can't offer."
    ),
    "enterprise-codemode": (
        "Hides the single call inside a sandboxed code block, which is harder to audit/log at "
        "the individual tool-call level than a plain ReAct turn — the wrong trade for a "
        "one-call, transparency-sensitive lookup."
    ),
    "enterprise-mcp-codemode": (
        "Same sandboxing-hides-the-call problem as enterprise-codemode, just via MCP transport."
    ),
    "enterprise-sql-react": (
        "Would need to rediscover the schema and hand-write SQL for something a maintained, "
        "documented MCP tool already answers in one typed call."
    ),
    "enterprise-sql-codemode": (
        "Same schema-rediscovery cost as sql-react, plus unnecessary sandbox overhead."
    ),
}
_MCPREACT_SIGNALS = [
    "Same shape as an enterprise-react question: single ID or small fixed filter, 1-3 calls.",
    "No fan-out — a router can't distinguish MCP-react from react from the question text alone; "
    "the deciding factor is deployment context (shared/centrally-hosted tool server, per-call "
    "audit trail requirement) rather than anything observable in the prompt.",
]

_MCPREACT_WHY = [
    (
        "mcpreact-customer-profile-155",
        "Single low-fan-out profile lookup — ideal for a one-call-per-turn, independently "
        "auditable MCP request.",
    ),
    (
        "mcpreact-product-detail-40",
        "One module lookup; the MCP protocol boundary makes this single call easy to log/replay "
        "independently.",
    ),
    (
        "mcpreact-low-adoption-threshold-15",
        "Single parameterized call with a clean audit trail per invocation.",
    ),
    (
        "mcpreact-top-modules-45days",
        "One-call ranking lookup — no batching needed, transparency of the single call is free.",
    ),
    (
        "mcpreact-recent-reviews-module-60",
        "Single reviews lookup, easily inspected as one discrete MCP call.",
    ),
    (
        "mcpreact-sales-summary-30d",
        "One aggregate call; suits a governance workflow that wants each data pull individually "
        "logged.",
    ),
    (
        "mcpreact-search-products-finance",
        "Single filtered search call with a clear, independently auditable request/response pair.",
    ),
    (
        "mcpreact-search-customers-silver-berlin",
        "One search call; no fan-out to hide inside a sandbox.",
    ),
    (
        "mcpreact-customer-orders-history-180",
        "Single order-history pull, well suited to a per-call audit boundary.",
    ),
    (
        "mcpreact-order-detail-900",
        "One order lookup; a natural fit for standardized, inspectable protocol calls.",
    ),
    (
        "mcpreact-customer-lifetime-value-110",
        "Single call matching the tool's own definition exactly — no ambiguity, no batching "
        "needed.",
    ),
    (
        "mcpreact-revenue-by-month-lastyear",
        "One-call yearly rollup; simple enough that ReAct's transparency costs nothing extra.",
    ),
]

# ═══════════════════════════════════════════════════════════════════════════
# enterprise-mcp-codemode
# ═══════════════════════════════════════════════════════════════════════════

_MCPCODEMODE_ALTERNATIVES = {
    "minimal": (
        "Has no tools at all — cannot enumerate or fetch any of the entities involved, MCP or "
        "otherwise, and can only guess or hallucinate."
    ),
    "enterprise-react": (
        "Same fan-out-over-many-serial-turns problem as react vs codemode, without any "
        "batching at all."
    ),
    "enterprise-codemode": (
        "Would answer just as correctly and slightly faster (no MCP hop) — MCP is worth it here "
        "only when the same tool layer must also be reachable by other bots/clients outside this "
        "one agent process, which is a deployment fact, not something in the question text."
    ),
    "enterprise-mcp-react": (
        "Same tools, but one MCP round trip per entity instead of one batched sandbox run — "
        "much slower for a double-digit fan-out."
    ),
    "enterprise-sql-react": (
        "Could answer via one aggregate query, but would need to re-derive per-entity business "
        "logic from scratch instead of reusing a tested MCP-served tool in a loop."
    ),
    "enterprise-sql-codemode": (
        "Same re-derivation risk as sql-react; loses the guaranteed-correct typed toolsemantics."
    ),
}
_MCPCODEMODE_SIGNALS = [
    "Same fan-out shape as an enterprise-codemode question (enumerated IDs, 'every'/'each', "
    "or a discover-then-fan-out chain over a double-digit population).",
    "Deployment context implies the tool layer is centrally hosted/shared across multiple "
    "agents or non-Python clients, so it should be served over MCP rather than registered "
    "directly in-process.",
]

_MCPCODEMODE_WHY = [
    (
        "mcpcodemode-silver-lifetime-scan",
        "Scans every silver-tier customer (dozens) — batched loop over MCP-served tools beats "
        "serial MCP round trips.",
    ),
    (
        "mcpcodemode-customer-batch-lookup",
        "20 explicit customer IDs to look up and filter, batched in one sandbox run.",
    ),
    (
        "mcpcodemode-module-review-gap-scan-rd",
        "Unknown-size R&D module list, each needing a reviews check — fan-out over a category "
        "filter.",
    ),
    (
        "mcpcodemode-order-batch-audit",
        "22 orders each need fetching and aggregating — one batched loop instead of 22 MCP "
        "round trips.",
    ),
    (
        "mcpcodemode-top-module-price-value",
        "Chained fan-out: rank top 10 modules, then compute a ratio per module — dependent "
        "second-stage loop.",
    ),
    (
        "mcpcodemode-silver-churn-scan",
        "Every silver-tier customer needs a recency check — same batched-scan pattern as "
        "gold-churn-scan.",
    ),
    (
        "mcpcodemode-highprice-lowrating-scan",
        "Unknown-size high-price module list, each needing an average-rating computation.",
    ),
    (
        "mcpcodemode-category-deployment-spread",
        "5 dependent per-category calls with client-side min/max/avg.",
    ),
    (
        "mcpcodemode-recent-multi-subscribers",
        "40 customers each need an order-history pull and recency filter.",
    ),
    ("mcpcodemode-bundle-scan", "20 orders each need line-item expansion and counting."),
    (
        "mcpcodemode-least-reviewed-deepdive",
        "Chained fan-out: rank all modules by review count ascending, then pull the earliest "
        "review per module.",
    ),
    (
        "mcpcodemode-recent-cohort-value",
        "Unknown-size recent-cohort of customers, each needing a lifetime-value computation.",
    ),
]

# ═══════════════════════════════════════════════════════════════════════════
# enterprise-sql-react
# ═══════════════════════════════════════════════════════════════════════════

_SQLREACT_ALTERNATIVES = {
    "minimal": (
        "Has no tools at all — cannot query the database in any form and can only guess or "
        "hallucinate a plausible-looking answer."
    ),
    "enterprise-react": (
        "Has execute_sql available too, but the larger 17-tool surface tempts the model toward "
        "an ill-fitting semantic tool first (e.g. get_customer_lifetime_value's delivered-only "
        "definition) before it falls back to SQL — extra turns and a real risk of a subtly wrong "
        "answer for a question no typed tool actually covers."
    ),
    "enterprise-codemode": (
        "Same distractor-tool risk as enterprise-react, plus unneeded sandbox overhead for a"
        "1-2 query answer."
    ),
    "enterprise-mcp-react": "Same distractor-tool risk as enterprise-react, via MCP transport.",
    "enterprise-mcp-codemode": (
        "Combines the distractor-tool risk with both MCP and sandbox overhead."
    ),
    "enterprise-sql-codemode": (
        "Correct, but pays sandbox overhead for something answerable in a single execute_sql call "
        "with an already-known schema — no multi-query batching benefit to capture."
    ),
}
_SQLREACT_SIGNALS = [
    "The question needs a join/filter/grouping shape that doesn't match any of the 13 semantic "
    "tools.",
    "Self-joins, multi-attribute cohorts, percentage-of-total, or 'find mismatches' style checks.",
    "Answerable with a single well-written SELECT — no need for multiple dependent queries.",
]

_SQLREACT_WHY = [
    (
        "sqlreact-module-affinity",
        "Self-join market-basket analysis — no typed tool computes module co-occurrence.",
    ),
    (
        "sqlreact-median-price",
        "Median has no typed-tool equivalent; a single SELECT (or two) answers it directly.",
    ),
    (
        "sqlreact-revenue-per-module-efficiency",
        "Custom ratio metric (revenue per module) that no semantic tool exposes.",
    ),
    (
        "sqlreact-cross-functional-power-users",
        "Multi-category-count-per-customer filter has no matching typed tool.",
    ),
    (
        "sqlreact-bundle-percentage",
        "A percentage-of-total computation over line-item counts — pure ad-hoc SQL.",
    ),
    (
        "sqlreact-tier-rating-gap",
        "Cross-tier rating comparison per module — a bespoke join no tool anticipates.",
    ),
    (
        "sqlreact-fast-movers",
        "Date-diff cohort filter between account creation and first order — ad-hoc by nature.",
    ),
    (
        "sqlreact-mom-active-users",
        "Month-over-month percentage change is a custom derived series, not a canned tool output.",
    ),
    (
        "sqlreact-data-integrity-check",
        "A self-consistency check comparing stored vs. computed totals — inherently a raw-SQL "
        "query.",
    ),
    (
        "sqlreact-city-subscription-value",
        "Per-city average-of-per-user-totals is a custom two-level aggregate no tool supports.",
    ),
    (
        "sqlreact-early-cohort-comparison",
        "Cohort-vs-rest comparison by account-creation date has no typed-tool equivalent.",
    ),
    (
        "sqlreact-rating-trend",
        "Comparing early-half vs. recent-half review averages per module is fully custom analysis.",
    ),
]

# ═══════════════════════════════════════════════════════════════════════════
# enterprise-sql-codemode
# ═══════════════════════════════════════════════════════════════════════════

_SQLCODEMODE_ALTERNATIVES = {
    "minimal": (
        "Has no tools at all — cannot fetch the underlying rows needed for the computation and "
        "can only guess or hallucinate a plausible-looking statistic."
    ),
    "enterprise-react": (
        "No typed tool comes close, and it would need many manual turns to fetch data and "
        "reason through the statistics by hand."
    ),
    "enterprise-codemode": (
        "Same lack of a matching typed tool; batches calls but still has no bulk-statistics "
        "endpoint to call."
    ),
    "enterprise-mcp-react": (
        "Same gap as enterprise-react, via MCP transport, without any batching for the "
        "multi-query + compute workflow."
    ),
    "enterprise-mcp-codemode": (
        "Can batch tool calls but has no way to compute correlation/stdev/Jaccard itself "
        "without falling back to the same SQL-in-sandbox approach."
    ),
    "enterprise-sql-react": (
        "Would have to express the whole multi-stage computation (or an approximation of it) as "
        "one mega-query — possible for some of these, error-prone or impossible for statistics "
        "like Pearson correlation or Jaccard similarity that SQL has no native function for."
    ),
}
_SQLCODEMODE_SIGNALS = [
    "The computation needs a statistic SQL can't express directly (correlation, stdev, Jaccard, "
    "log-weighted score).",
    "Multiple dependent queries feed into a single downstream computation or ranking.",
    "An explicit formula is given in the prompt that mixes several fetched quantities together.",
]

_SQLCODEMODE_WHY = [
    (
        "sqlcodemode-rating-distribution-top5",
        "Two-stage query (find top 5, then per-module rating histogram) naturally fits "
        "fetch-then-shape-in-code.",
    ),
    (
        "sqlcodemode-price-rating-correlation",
        "Pearson correlation has no SQL-native function; fetch pairs, compute with Python's "
        "statistics module.",
    ),
    (
        "sqlcodemode-subscription-outliers",
        "Mean/stdev-based outlier detection is a two-stage fetch-then-filter computation.",
    ),
    (
        "sqlcodemode-customer-spend-jump",
        "Requires per-customer monthly rollups then a max-delta scan across consecutive months "
        "— not one SQL aggregate.",
    ),
    (
        "sqlcodemode-price-consistency-by-function",
        "Coefficient of variation (stdev/mean) per category needs Python-side division after "
        "aggregate fetch.",
    ),
    (
        "sqlcodemode-subscription-cadence",
        "Average gap between consecutive dates per customer is a sequential computation, not a "
        "SQL aggregate.",
    ),
    (
        "sqlcodemode-weighted-quality-score",
        "The formula uses ln(), which needs Python's math module after fetching the raw values.",
    ),
    (
        "sqlcodemode-unreviewed-below-median",
        "Median has no SQL-native function; needs a fetch-then-compute-then-filter pipeline.",
    ),
    (
        "sqlcodemode-gold-category-overlap",
        "Jaccard similarity across all pairs of 5 customers needs set operations in code, not SQL.",
    ),
    (
        "sqlcodemode-seat-normalization-simulation",
        "A what-if simulation (re-deriving revenue with a hypothetical seat count) is "
        "inherently a compute step, not a stored query.",
    ),
    (
        "sqlcodemode-revenue-momentum",
        "Requires 5 categories x 12 months of dependent queries reduced to a single ratio per "
        "category.",
    ),
    (
        "sqlcodemode-composite-engagement-score",
        "The explicit multi-component formula mixes three separately-fetched quantities that "
        "must be combined in code.",
    ),
]

# ═══════════════════════════════════════════════════════════════════════════
# minimal
# ═══════════════════════════════════════════════════════════════════════════

_MINIMAL_ALTERNATIVES = {
    "enterprise-react": (
        "Correct but wasteful — the model must first reason about which of 17 tools (if any) "
        "applies, then discover none of them are relevant, before answering from its own "
        "reasoning anyway."
    ),
    "enterprise-codemode": (
        "Same wasted tool-selection step as enterprise-react, plus an unused Monty sandbox "
        "spin-up for a question that never needed a tool call in the first place."
    ),
    "enterprise-mcp-react": (
        "Same wasted tool-selection step as enterprise-react, plus a live MCP server connection "
        "that is never actually called."
    ),
    "enterprise-mcp-codemode": (
        "Combines every source of unnecessary overhead: MCP connection setup, sandbox spin-up, "
        "and tool-selection reasoning for tools that are structurally guaranteed to go unused."
    ),
    "enterprise-sql-react": (
        "The model may burn a turn on list_tables/describe_table looking for relevant data "
        "before realizing the question is self-contained and needs no query at all."
    ),
    "enterprise-sql-codemode": (
        "Same wasted schema-discovery risk as sql-react, plus sandbox overhead for a question "
        "that never touches the database."
    ),
}
_MINIMAL_SIGNALS = [
    "All numbers/entities needed to answer are already given in the question text itself.",
    "No mention of customers, products, orders, subscriptions, revenue, or any other database "
    "entity.",
    "The task is a closed-form calculation, text transformation, or logic puzzle solvable by "
    "reasoning alone.",
    "Nothing in the question implies looking anything up — it implies computing or reasoning "
    "over inputs already supplied.",
    "The message is small talk, a greeting, or a meta/FAQ question about the assistant itself "
    "('hello', 'what's up', 'what can you help with') rather than a request for any data.",
]

_MINIMAL_WHY = [
    (
        "minimal-percentage-discount",
        "Pure arithmetic on numbers already in the prompt — no lookup of any kind is needed.",
    ),
    (
        "minimal-compound-interest",
        "A standard compound-interest formula applied to given inputs; no external data required.",
    ),
    (
        "minimal-list-statistics",
        "Mean/median/stdev of an explicitly given list — a closed-form calculation.",
    ),
    (
        "minimal-string-reversal-vowels",
        "Pure string manipulation on a literal given in the prompt.",
    ),
    (
        "minimal-date-formatting",
        "Reformatting a literal date string — no database or tool access involved.",
    ),
    (
        "minimal-fizzbuzz-range",
        "A self-contained numeric filter over a fixed range — classic no-tool reasoning.",
    ),
    (
        "minimal-caesar-cipher",
        "Deterministic character-shift encoding of a literal word — pure text transformation.",
    ),
    (
        "minimal-palindrome-check",
        "Cleaning and comparing a literal phrase to its reverse — no external data needed.",
    ),
    (
        "minimal-gcd-lcm",
        "Elementary number theory on two given integers — closed-form, no lookup.",
    ),
    (
        "minimal-word-count-unique",
        "Counting words in a literal sentence — pure text processing.",
    ),
    (
        "minimal-unit-conversion",
        "A given conversion factor applied to a given value — single-step arithmetic.",
    ),
    (
        "minimal-marble-probability",
        "Classic probability computation from counts given directly in the prompt.",
    ),
    (
        "minimal-greeting-howareyou",
        "Pure small talk with no factual claim to verify — any tool call would be a routing "
        "mistake, not just wasted overhead.",
    ),
    (
        "minimal-greeting-whatsup",
        "Casual greeting with nothing to look up — a plain conversational reply is correct by "
        "definition.",
    ),
    (
        "minimal-faq-capabilities",
        "A meta question about the assistant itself, not about any data the enterprise tools "
        "expose.",
    ),
]

ROUTING_BENCHMARK: dict[str, list[dict[str, Any]]] = {
    "minimal": _build_group(
        "minimal", "minimal", _MINIMAL_WHY, _MINIMAL_ALTERNATIVES, _MINIMAL_SIGNALS
    ),
    "enterprise-react": _build_group(
        "react", "enterprise-react", _REACT_WHY, _REACT_ALTERNATIVES, _REACT_SIGNALS
    ),
    "enterprise-codemode": _build_group(
        "codemode", "enterprise-codemode", _CODEMODE_WHY, _CODEMODE_ALTERNATIVES, _CODEMODE_SIGNALS
    ),
    "enterprise-mcp-react": _build_group(
        "mcpreact", "enterprise-mcp-react", _MCPREACT_WHY, _MCPREACT_ALTERNATIVES, _MCPREACT_SIGNALS
    ),
    "enterprise-mcp-codemode": _build_group(
        "mcpcodemode",
        "enterprise-mcp-codemode",
        _MCPCODEMODE_WHY,
        _MCPCODEMODE_ALTERNATIVES,
        _MCPCODEMODE_SIGNALS,
    ),
    "enterprise-sql-react": _build_group(
        "sqlreact", "enterprise-sql-react", _SQLREACT_WHY, _SQLREACT_ALTERNATIVES, _SQLREACT_SIGNALS
    ),
    "enterprise-sql-codemode": _build_group(
        "sqlcodemode",
        "enterprise-sql-codemode",
        _SQLCODEMODE_WHY,
        _SQLCODEMODE_ALTERNATIVES,
        _SQLCODEMODE_SIGNALS,
    ),
}


# ═══════════════════════════════════════════════════════════════════════════
# Decision-boundary analysis
# ═══════════════════════════════════════════════════════════════════════════

ANALYSIS: dict[str, dict[str, Any]] = {
    "minimal_vs_any_tool_architecture": {
        "summary": (
            "minimal is a plain agent with zero tools and zero harness capabilities. It is not "
            "part of the Enterprise Decision Intelligence benchmark family (it cannot answer any "
            "question that needs data from the SQLite database) but it is the correct choice for "
            "the subset of requests that need no data lookup at all — every one of the six "
            "enterprise architectures pays tool-selection reasoning (and, for CodeMode/MCP "
            "variants, sandbox or transport setup) for tools that go structurally unused."
        ),
        "choose_minimal_when": [
            "Every number/entity needed to answer is already present in the question text.",
            "No customer, product, order, subscription, or revenue entity is referenced.",
            "The task is closed-form arithmetic, text transformation, or logic reasoning.",
        ],
        "choose_any_enterprise_architecture_when": [
            "The question references or implies looking up data that lives in the enterprise "
            "database (a specific customer, product, order, or an aggregate over any of them) — "
            "minimal cannot answer these at all and can only guess or hallucinate.",
        ],
        "measurable_signal": (
            "Whether the question mentions or implies any database entity. If none, minimal "
            "answers in one model turn with no tool-selection overhead; if one is referenced, "
            "minimal has no way to answer correctly and one of the six enterprise architectures "
            "must be used instead."
        ),
    },
    "enterprise-react_vs_enterprise-codemode": {
        "summary": (
            "Both use the same 17 typed tools registered directly in-process. The only variable "
            "is execution pattern: one tool call per model turn (ReAct) vs. batching many calls "
            "inside one Monty-sandboxed run_code call (CodeMode)."
        ),
        "choose_react_when": [
            "The question needs 1-3 tool calls with no iteration over a list of entities.",
            "The answer shape matches a single typed tool's return value directly.",
            "Low latency for a simple lookup matters more than batching efficiency.",
        ],
        "choose_codemode_when": [
            "The question enumerates or implies iteration over 10+ entities.",
            "A first tool call's result determines the arguments for many follow-up calls "
            "(discover-then-fan-out chains).",
            "Client-side aggregation/filtering across many tool results is required.",
        ],
        "measurable_signal": (
            "Count of distinct tool calls needed to answer correctly: ReAct's cost scales "
            "linearly with model round trips (one per call); CodeMode's cost is ~flat "
            "(one round trip) regardless of call count, at the fixed price of one sandbox "
            "execution."
        ),
    },
    "enterprise-mcp-react_vs_enterprise-mcp-codemode": {
        "summary": (
            "Identical to the react-vs-codemode boundary above, but with tools served over the "
            "local FastMCP server instead of direct registration — every call additionally pays "
            "an MCP transport hop."
        ),
        "choose_mcp_react_when": [
            "Same low-call-count conditions as enterprise-react.",
            "Per-call auditability matters more than raw latency (each MCP call is a discrete, "
            "independently loggable request/response pair; CodeMode hides calls inside a "
            "sandboxed script).",
        ],
        "choose_mcp_codemode_when": [
            "Same fan-out conditions as enterprise-codemode.",
            "The tool layer must stay centrally hosted/shared (e.g. reused by other bots or "
            "non-Python clients) while still needing batching efficiency for heavy workloads.",
        ],
        "measurable_signal": (
            "Same tool-call-count signal as react vs codemode, plus a fixed per-call MCP "
            "serialization/transport overhead that compounds fastest in enterprise-mcp-react "
            "for high-call-count questions — the strongest empirical evidence to route those to "
            "enterprise-mcp-codemode instead."
        ),
    },
    "enterprise-sql-react_vs_enterprise-sql-codemode": {
        "summary": (
            "Both have only list_tables, describe_table, and execute_sql — no semantic tools, "
            "no get_schema_context cheat sheet. The variable is whether schema discovery + query "
            "writing happens across several ReAct turns or inside one batched CodeMode script."
        ),
        "choose_sql_react_when": [
            "A single well-written SELECT (or CTE) fully answers the question.",
            "The schema is either already known to the model or trivial to infer from one "
            "describe_table call.",
        ],
        "choose_sql_codemode_when": [
            "The answer needs several dependent queries whose results feed a downstream "
            "computation (e.g. correlation, standard deviation, Jaccard similarity, or a "
            "custom weighted formula) that SQL cannot express natively.",
            "Schema discovery plus multiple exploratory queries should happen in one round trip "
            "rather than several back-and-forth turns.",
        ],
        "measurable_signal": (
            "Number of distinct SQL statements required and whether any post-query arithmetic "
            "beyond what SQL can express natively (stdev, correlation, set operations) is needed."
        ),
    },
    "direct_typed_tools_vs_local_fastmcp_tools": {
        "summary": (
            "enterprise-react/enterprise-codemode register the same Python functions directly on "
            "the agent; enterprise-mcp-react/enterprise-mcp-codemode expose the identical "
            "functions through a local FastMCP server. Tool behavior and correctness are "
            "identical either way — this is purely a deployment/operational decision, not a "
            "capability difference."
        ),
        "choose_direct_when": [
            "Single-process deployment with no need to share the tool layer across agents/clients.",
            "Minimizing latency and moving parts matters (no serialization/transport hop).",
        ],
        "choose_mcp_when": [
            "The same tool implementations need to be reachable by multiple agents, models, or "
            "non-Python clients from one centrally maintained server.",
            "Per-call protocol-level auditability/standardization is a requirement (e.g. "
            "compliance or governance workflows that need an inspectable request/response log "
            "per tool invocation).",
        ],
        "measurable_signal": (
            "Not observable from the question text alone — this boundary is a deployment fact "
            "(is the tool layer centrally hosted / shared / required to be independently "
            "auditable?), not a property of any individual user request."
        ),
    },
    "full_enterprise_tools_vs_sql_only_tools": {
        "summary": (
            "enterprise-react/enterprise-codemode/enterprise-mcp-* get 13 semantic tools plus "
            "list_tables/describe_table/execute_sql/get_schema_context (17 total, a strict "
            "superset). enterprise-sql-react/enterprise-sql-codemode intentionally get only "
            "list_tables, describe_table, and execute_sql — no semantic tools and no "
            "get_schema_context business-metric cheat sheet."
        ),
        "choose_full_enterprise_tools_when": [
            "The question matches an existing semantic tool's exact shape (a canned lookup, "
            "search, or aggregate) — the typed tool is faster and encodes the correct business "
            "logic (e.g. which order statuses count toward 'activation' or 'lifetime value') so "
            "the model can't get a subtle metric definition wrong.",
        ],
        "choose_sql_only_when": [
            "The question needs a join/filter/grouping shape no semantic tool anticipates "
            "(self-joins, multi-attribute cohorts, custom ratios, data-integrity checks).",
            "A smaller tool surface (3 tools instead of 17) is preferred to remove the risk of "
            "the model reaching for a misleadingly-named semantic tool (e.g. "
            "get_customer_lifetime_value's delivered-only definition) when the user's intended "
            "definition is broader or different.",
        ],
        "measurable_signal": (
            "Whether any of the 13 semantic tools' documented parameters and return shape "
            "actually match what's being asked. If none do, SQL-only removes a real distractor "
            "risk that the full tool set carries; if one does, the full tool set answers faster "
            "and more reliably."
        ),
    },
}
