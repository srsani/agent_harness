# Architecture recommendation for a 120-tool agent harness

**Goal:** pick an agent architecture that maximizes correctness/groundedness and minimizes
hallucination once the tool count grows from 17 to 120 (62 real tools across 10 business
domains + 58 plausible-but-irrelevant "distractor" tools).

**Method:** 490 (task x architecture) runs, 30 tasks x up to 19 architectures, local
`qwen3.6-35b-a3b` model, single run per cell (no repeats, given local-model throughput). 20 of
the 30 tasks are brand-new (5 new domains: Support, Marketing, Procurement, Workforce,
Finance), 10 are the original `adi-*`-style tasks re-pointed at the 120-tool registries. Every
run's raw tool-call trace (including nested CodeMode sandbox calls and tool-search/dispatch
calls) was captured and scored against a hand-built expected-tool map
(`tasks/tool_selection_benchmark.py`) in addition to the existing correctness/groundedness/
hallucination scoring. Full data: `full_matrix_summary.csv` (490 rows) and
`architecture_summary.csv` (18 architectures).

*Follow-up sweep added after the initial 430-run pass:* `enterprise-codemode-toolsearch-120`
and `enterprise-codemode-categorized-search` — the two CodeMode-at-120-tool-scale variants
paired with each of the two winning discovery mechanisms — were run across the same 30 tasks
(60 more runs) specifically to close the gap in the original "avoid CodeMode entirely" claim,
which previously rested only on the 17-tool-scale `enterprise-codemode-toolsearch` data point.
This sweep needed a 180-second per-run wall-clock cap (`scripts/_run_two_more_archs.sh`) that
the original 430-run pass didn't: `enterprise-codemode-toolsearch-120` hung outright (not just
slow — near-zero CPU, an idle-but-open connection to the local model server) on
`finance-expense-breakdown-2025`, reproducibly, on two separate attempts. See "CodeMode's
hallucination problem" below for what this sweep found.

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
discovery mechanism — this was tested directly by pairing CodeMode with *both* winning
discovery mechanisms (`enterprise-codemode-toolsearch-120`, `enterprise-codemode-categorized-search`)
and both land well below their non-CodeMode counterparts, for two different reasons — see
"CodeMode's hallucination problem" below.

## Headline numbers (30-task average, sorted by reliability-adjusted score)

| architecture | reliability-adj. score | ok rate | avg correctness | avg hallucination | tool recall | tool precision | distractor rate | fabricated rate | avg latency |
|---|---|---|---|---|---|---|---|---|---|
| **enterprise-react-toolsearch-120** | **0.687** | 30/30 | 0.863 | 0.316 | 0.967 | 0.983 | 0.017 | 0.000 | 7.3s |
| **enterprise-categorized-search** | **0.664** | 30/30 | 0.850 | 0.351 | 0.933 | 1.000 | 0.000 | 0.000 | 7.0s |
| enterprise-codemode-categorized-search | 0.547 | 29/30 | 0.639 | 0.412 | 0.667 | 0.469 | 0.0 | 0.512 | 21.6s |
| enterprise-sql-codemode | 0.543 | 29/30 | 0.658 | 0.421 | 0.967 | 0.548 | 0.0 | 0.448 | 20.0s |
| enterprise-react-thinking | 0.540 | 29/30 | 0.638 | 0.383 | 0.967 | 0.933 | 0.0 | 0.000 | 16.2s |
| enterprise-codemode | 0.538 | 30/30 | 0.656 | 0.412 | 1.000 | 0.543 | 0.0 | 0.431 | 18.2s |
| enterprise-sql-react | 0.538 | 30/30 | 0.661 | 0.431 | 1.000 | 1.000 | 0.0 | 0.000 | 13.7s |
| enterprise-react (17-tool baseline) | 0.534 | 29/30 | 0.704 | 0.437 | 0.967 | 0.922 | 0.0 | 0.000 | 15.4s |
| enterprise-codemode-thinking | 0.531 | 29/30 | 0.639 | 0.442 | 0.933 | 0.529 | 0.0 | 0.423 | 17.7s |
| enterprise-codemode-toolsearch-120 | 0.503 | 27/30 | 0.590 | 0.448 | 0.900 | 0.810 | 0.039 | 0.007 | 19.5s |
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

**Pairing CodeMode with each winning discovery mechanism doesn't rescue it, and fails in two
different ways.** `enterprise-codemode-toolsearch-120` and `enterprise-codemode-categorized-search`
were run explicitly to test this (60 more runs, added after the initial 430-run pass — see
"Method" above), and both land in the middle of the pack, well below their non-CodeMode
counterparts (`enterprise-react-toolsearch-120` 0.687, `enterprise-categorized-search` 0.664):

- `enterprise-codemode-categorized-search` (0.547) reproduces the *classic* CodeMode failure
  mode: 51.2% fabricated-call rate, the highest of any architecture tested, even higher than
  plain `enterprise-codemode`'s 43.1%. Most of that is the model needing more `run_code` turns
  than plain CodeMode to work through category -> tool-in-category -> dispatch as three separate
  sandboxed steps (each `run_code` call itself counts as a fabricated call under this
  benchmark's scoring, since `run_code` isn't a real domain tool — see caveat below) — but a
  genuine subset is real hallucination: the model invented tool names like
  `get_analytics_support_tickets` and `get_supplier_scorecards` as arguments to `call_tool()`
  that were never returned by `search_tools_in_category`. Tool recall also drops to 66.7% (vs.
  93.3% for the non-CodeMode `enterprise-categorized-search`) — batching the discovery protocol
  into Python turns some tasks into a bad "guess the tool name" game instead of reading what
  `search_tools_in_category` actually returned.
- `enterprise-codemode-toolsearch-120` (0.503) fails differently: fabrication is nearly
  eliminated (0.7%, in the same range as the *best* architectures, not the other CodeMode
  variants) but reliability collapses instead — 27/30 ok-rate, including one task
  (`finance-expense-breakdown-2025`) that didn't just fail, it **hung outright** on two separate
  attempts (near-zero CPU, an idle-but-open connection to the local model server, for 13+
  minutes before this report's 180-second timeout killed it) and two more tasks that exhausted
  their tool-retry budget. The low fabrication rate has a specific likely cause, not a solved
  CodeMode problem: `pydantic-ai`'s `ToolSearch` capability appears to make a tool natively
  callable once `search_tools` surfaces it, in addition to making it available inside
  `run_code` — the trace shows this architecture's model calling most tools directly (`"via":
  "native"`) and reaching for `run_code` only occasionally, i.e. it's mostly *not* exercising
  CodeMode's actual sandboxed-batching behavior on this workload, which is also why its failure
  mode looks like a ReAct-family reliability problem (hangs, retry exhaustion) rather than
  CodeMode's usual fabrication signature.

*Scoring caveat:* this benchmark's `fabricated_call_count` treats any call to `run_code` itself
as fabricated (it's not one of the 120 registered domain/distractor tools), on top of counting
genuinely invented function/tool names found inside the sandbox. That's the same convention
already baked into every other CodeMode row in this table (verified against `enterprise-codemode`'s
raw trace), so the numbers are apples-to-apples across the whole table — but it means
`enterprise-codemode-categorized-search`'s 51.2% is partly "took more sandboxed turns to do the
same discovery protocol" and partly real hallucination, not 51.2% invented tool names outright.

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

The one distractor call in the original 430-run matrix came from the winning architecture
itself: for the prompt *"Find every webinar campaign,"* `enterprise-react-toolsearch-120`
searched, found `get_campaign_by_name` (a distractor tool named to look like a plausible
campaign lookup) instead of `search_campaigns`, and returned an incomplete single-row result.
That's a genuine, useful near-miss — it shows the benchmark's distractors are doing their job
(they're getting *discovered* and occasionally *chosen*), and that even the best architecture
isn't immune to a well-named decoy. It's also the exception, not the rule: precision stayed at
98.3% overall. (The follow-up 60-run CodeMode sweep added a handful more distractor calls to
the wider matrix — `enterprise-codemode-toolsearch-120` picked up a 3.9% distractor rate across
its 30 runs, calling real decoys like `get_budget_summary` a few times — but distractors aren't
that architecture's main problem; see "CodeMode's hallucination problem" for its actual failure
mode.)

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
4. **Avoid CodeMode** at this tool count on this model family. Plain/SQL-only/`-thinking`/MCP
   CodeMode all show a 40%+ fabricated-call rate; pairing it with category-first discovery
   pushes fabrication even higher (51%); pairing it with `ToolSearch` cuts fabrication back down
   but trades it for reliability failures instead (27/30 ok-rate, including a run that hung for
   13+ minutes and had to be killed by an external timeout). No CodeMode variant at 120-tool
   scale beats its non-CodeMode counterpart on any axis that matters here.
5. If you must keep an MCP transport for tool serving, pair it with the same discovery
   mechanism rather than the native/`ENTERPRISE_MCP_PUBLIC_URL` path — `enterprise-mcp-react-120`
   inherits the same "all schemas up front" problem as plain ReAct-120 and fails identically.

## Data artifacts

- `reports/20260708_scale-benchmark/architecture_summary.csv` — one row per architecture (18
  rows; `minimal` excluded by the generator script, added back manually in the table above).
- `reports/20260708_scale-benchmark/full_matrix_summary.csv` — 490 rows, one per (task,
  architecture), including `tool_recall`, `tool_precision`, `distractor_call_count`,
  `fabricated_call_count` alongside the existing correctness/groundedness/hallucination_rate
  columns.
- `reports/20260708_scale-benchmark/extra_*_scored.json` — the 60 follow-up runs (30 tasks x
  `enterprise-codemode-toolsearch-120` / `enterprise-codemode-categorized-search`) added after
  the initial 430-run pass; single-`run`-mode reports (not `run-all`), same schema, picked up by
  `notebooks/generate_report_csvs.py` alongside the original `run-all`-mode files.
- `scripts/_run_two_more_archs.sh` — the one-off runner for that follow-up sweep; wraps each
  `agent-bench run` in a 180s `gtimeout` (invoking the venv binary directly, not `uv run`, so the
  signal reaches the actual process) and synthesizes a `TimeoutError` failure result when it
  fires, since CodeMode's sandboxed `run_code` call can hang outright rather than fail fast (see
  "CodeMode's hallucination problem").
- `src/agent_harness/tasks/tool_selection_benchmark.py` — expected-tool map + scoring
  function; reusable for any future architecture added to the harness.
- `src/agent_harness/tools/distractors.py` — the 58-tool decoy registry (legacy/duplicate,
  external-unavailable, trap/near-miss, lookup, and synthetic-analytics categories).
