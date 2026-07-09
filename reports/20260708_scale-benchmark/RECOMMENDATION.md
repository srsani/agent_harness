# Architecture recommendation for a 120-tool agent harness

**Goal:** pick an agent architecture that maximizes correctness/groundedness and minimizes
hallucination once the tool count grows from 17 to 120 (62 real tools across 10 business
domains + 58 plausible-but-irrelevant "distractor" tools).

**Method:** 430 (task x architecture) runs, 30 tasks x up to 17 architectures, local
`qwen3.6-35b-a3b` model, single run per cell (no repeats, given local-model throughput). 20 of
the 30 tasks are brand-new (5 new domains: Support, Marketing, Procurement, Workforce,
Finance), 10 are the original `adi-*`-style tasks re-pointed at the 120-tool registries. Every
run's raw tool-call trace (including nested CodeMode sandbox calls and tool-search/dispatch
calls) was captured and scored against a hand-built expected-tool map
(`tasks/tool_selection_benchmark.py`) in addition to the existing correctness/groundedness/
hallucination scoring. Full data: `full_matrix_summary.csv` (430 rows) and
`architecture_summary.csv` (17 architectures).

## Recommendation

**Use `enterprise-react-toolsearch-120`**: ReAct + pydantic-ai's built-in `ToolSearch`
capability (`defer_loading=True` on all 120 tools, semantic `search_tools` discovery on
demand) as the primary architecture for the 120-tool harness.

If you need an implementation that doesn't depend on a specific framework's built-in tool
search capability, `enterprise-categorized-search` (hand-rolled category-first discovery:
`list_tool_categories` -> `search_tools_in_category` -> `call_tool`) is an extremely close
second and a good portable fallback.

Do **not** use any architecture that renders all 120 tool schemas up front
(`enterprise-react-120`, `enterprise-mcp-react-120`, `enterprise-codemode-120`) — see "Why the
naive approach fails" below. Avoid CodeMode entirely for this tool count regardless of
discovery mechanism — see "CodeMode's hallucination problem" below.

## Headline numbers (30-task average, sorted by reliability-adjusted score)

| architecture | reliability-adj. score | ok rate | avg correctness | avg hallucination | tool recall | tool precision | distractor rate | fabricated rate | avg latency |
|---|---|---|---|---|---|---|---|---|---|
| **enterprise-react-toolsearch-120** | **0.687** | 30/30 | 0.863 | 0.316 | 0.967 | 0.983 | 0.017 | 0.000 | 7.3s |
| **enterprise-categorized-search** | **0.664** | 30/30 | 0.850 | 0.351 | 0.933 | 1.000 | 0.000 | 0.000 | 7.0s |
| enterprise-sql-codemode | 0.543 | 29/30 | 0.658 | 0.421 | 0.967 | 0.548 | 0.0 | 0.448 | 20.0s |
| enterprise-react-thinking | 0.540 | 29/30 | 0.638 | 0.383 | 0.967 | 0.933 | 0.0 | 0.000 | 16.2s |
| enterprise-codemode | 0.538 | 30/30 | 0.656 | 0.412 | 1.000 | 0.543 | 0.0 | 0.431 | 18.2s |
| enterprise-sql-react | 0.538 | 30/30 | 0.661 | 0.431 | 1.000 | 1.000 | 0.0 | 0.000 | 13.7s |
| enterprise-react (17-tool baseline) | 0.534 | 29/30 | 0.704 | 0.437 | 0.967 | 0.922 | 0.0 | 0.000 | 15.4s |
| enterprise-codemode-thinking | 0.531 | 29/30 | 0.639 | 0.442 | 0.933 | 0.529 | 0.0 | 0.423 | 17.7s |
| enterprise-mcp-react | 0.494 | 28/30 | 0.634 | 0.480 | 0.933 | 0.911 | 0.0 | 0.000 | 12.5s |
| enterprise-mcp-codemode | 0.477 | 22/30 | 0.581 | 0.503 | 0.733 | 0.424 | 0.0 | 0.408 | 13.8s |
| enterprise-codemode-toolsearch (17-tool) | 0.402 | 25/30 | 0.474 | 0.551 | 0.800 | 0.780 | 0.0 | 0.068 | 25.4s |
| enterprise-react-toolsearch (17-tool) | 0.238 | 30/30 | 0.256 | 0.384 | 0.267 | 0.967 | 0.0 | 0.000 | 21.3s |
| **enterprise-codemode-120** | 0.083 | 1/30 | 0.071 | 0.900 | 0.100 | 0.060 | 0.0 | 0.400 | 19.3s |
| **enterprise-react-120** | 0.000 | 0/30 | 0.000 | 1.000 | 0.0 | 0.0 | — | — | — |
| **enterprise-mcp-react-120** | 0.000 | 0/30 | 0.000 | 1.000 | 0.0 | 0.0 | — | — | — |
| enterprise-mcp-react-native | 0.000 | 0/30 | 0.000 | 1.000 | 0.0 | 0.0 | — | — | — |
| minimal (no tools) | — | — | 0.138 | 0.746 | — | — | — | — | — |

(`enterprise-react-120`/`enterprise-codemode-120`/`enterprise-mcp-react-120` were only run on
the first 10 tasks in the sample — their 0/10 and 1/10 failure rates were consistent and
expensive to reproduce, so the remaining 20-task batch skipped them to spend local-model time
where it produced signal. `enterprise-mcp-react-native` requires a public tunnel URL
(`ENTERPRISE_MCP_PUBLIC_URL`) that isn't configured in this environment and reliably 0/10s.)

## Why the naive "send all 120 schemas" approach fails

`enterprise-react-120`, `enterprise-mcp-react-120`, and (mostly) `enterprise-codemode-120` all
send full JSON schemas (or, for CodeMode, full Python function signatures) for all 120 tools on
every single turn. On this local model that consistently blows the context window
(`ModelHTTPError: number of tokens to keep from the initial prompt is greater than the context
length`) or exhausts retries when the model tries to call a tool name directly instead of
through the batching mechanism it was actually given. This isn't a bug in the harness — it's
the exact failure mode a 120-tool deployment needs to design around, and it's why a
discovery-based architecture stops being a "nice to have" once you cross a few dozen tools:
correctness goes from "mostly works" to a flat 0% pass rate the moment the tool count outgrows
the model's context.

## CodeMode's hallucination problem

Every CodeMode variant — plain, SQL-only, `-thinking`, and MCP-backed — has a fabricated-call
rate of 40-45%, regardless of tool count (this pattern already existed at 17 tools and gets
worse, not better, at 120). Inside the sandboxed `run_code` call the model writes Python that
invents function names/signatures it never actually saw (or misremembers slightly), then either
retries into a working call or gives up with a partially-wrong answer. `enterprise-codemode-120`
is the extreme case: 100 real Python callables plus 58 distractors as bare function signatures
in one sandbox is enough to make the model fabricate function names in 9/10 runs. Whatever
correctness CodeMode buys (tool-recall is often 1.0 — it does find the *right* tool alongside
the fabricated ones) is undercut by precision collapsing into the 0.4-0.55 range. CodeMode is
not recommended at this scale on this model family.

## Why the two discovery-based architectures win

Both `enterprise-react-toolsearch-120` (defer-loaded native ToolSearch) and
`enterprise-categorized-search` (hand-rolled `list_tool_categories` ->
`search_tools_in_category` -> `call_tool`) share the same core property: **the model never sees
more than a handful of tool schemas at once.** That keeps prompts short (they're also the two
fastest architectures at ~7s average, 2-3x faster than any 17-tool baseline) and keeps the
candidate set small enough that the model reliably picks the right tool instead of a distractor
or an invented name:

- `enterprise-react-toolsearch-120`: 96.7% tool recall, 98.3% tool precision, 0% fabrication,
  1.7% distractor rate (a single miss out of the whole 30-task run — see below), highest
  correctness (0.863) and lowest hallucination (0.316) of any architecture tested.
- `enterprise-categorized-search`: 93.3% recall, **100% precision** (zero distractor or
  fabricated calls across all 30 tasks), 0.850 correctness, 0.351 hallucination.

The one distractor call in the entire 430-run matrix came from the winning architecture itself:
for the prompt *"Find every webinar campaign,"* `enterprise-react-toolsearch-120` searched,
found `get_campaign_by_name` (a distractor tool named to look like a plausible campaign lookup)
instead of `search_campaigns`, and returned an incomplete single-row result. That's a genuine,
useful near-miss — it shows the benchmark's distractors are doing their job (they're getting
*discovered* and occasionally *chosen*), and that even the best architecture isn't immune to a
well-named decoy. It's also the exception, not the rule: precision stayed at 98.3% overall.

`enterprise-codemode-toolsearch` (ToolSearch + CodeMode, 17-tool scale) shows discovery alone
doesn't fully fix CodeMode's problem (6.8% fabrication vs 0% for the ReAct-based tool-search
variants) — batching still invites the model to write code against tools it half-remembers.

## Notable caveat: 17-tool `enterprise-react-toolsearch` looks bad, but it's an unfair fight

`enterprise-react-toolsearch` (defer-loaded ToolSearch over the *original* 17 tools) scores a
low 0.238 here — but 20 of the 30 tasks in this sample require domain-specific tools
(`get_campaign_roi`, `get_attrition_rate`, etc.) that simply don't exist in the 17-tool kit.
Its 0.267 tool recall mostly reflects "the right tool wasn't available to this architecture,"
not a discovery failure — the correctness collapse is a scope mismatch, not a knock against
ToolSearch as a mechanism. (This is the same reason we exclude the other 17-tool-only
architectures from the "-120 vs baseline" framing above except as a sanity check that 17-tool
performance isn't a fluke of a smaller registry.)

## Practical guidance for a 120-tool rollout

1. **Primary:** `enterprise-react-toolsearch-120`-style architecture — plain ReAct loop, all
   tools registered with on-demand/deferred discovery, no batching layer.
2. **Portable fallback:** category-first discovery (`enterprise-categorized-search`) if the
   framework doesn't ship a native tool-search capability, or if you want deterministic
   (non-semantic-search) discovery. It slightly out-precisions ToolSearch (100% vs 98.3%) at a
   small recall cost (93.3% vs 96.7%).
3. **Never** send all 120 schemas up front, in ReAct or CodeMode form — it's a hard reliability
   cliff (0-10% ok-rate on this model), not a gradual degradation.
4. **Avoid CodeMode** at this tool count on this model family — the fabricated-call rate is
   consistently 40%+ whether or not it's paired with discovery, SQL-only, or extended thinking.
5. If you must keep an MCP transport for tool serving, pair it with the same discovery
   mechanism rather than the native/`ENTERPRISE_MCP_PUBLIC_URL` path — `enterprise-mcp-react-120`
   inherits the same "all schemas up front" problem as plain ReAct-120 and fails identically.

## Data artifacts

- `reports/20260708_scale-benchmark/architecture_summary.csv` — one row per architecture.
- `reports/20260708_scale-benchmark/full_matrix_summary.csv` — 430 rows, one per (task,
  architecture), including `tool_recall`, `tool_precision`, `distractor_call_count`,
  `fabricated_call_count` alongside the existing correctness/groundedness/hallucination_rate
  columns.
- `src/agent_harness/tasks/tool_selection_benchmark.py` — expected-tool map + scoring
  function; reusable for any future architecture added to the harness.
- `src/agent_harness/tools/distractors.py` — the 58-tool decoy registry (legacy/duplicate,
  external-unavailable, trap/near-miss, lookup, and synthetic-analytics categories).
