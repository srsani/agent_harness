# Agent Harness Bench

Compare **agent harnesses** (capability libraries) against **agentic architectures** (orchestration patterns) using shared tasks and a realistic enterprise Decision Intelligence database.

Current harness: [pydantic-ai-harness](https://github.com/pydantic/pydantic-ai-harness) on top of [Pydantic AI](https://ai.pydantic.dev/).

---

## Quick start

Requires [uv](https://docs.astral.sh/uv/) and Python 3.10+.

```bash
# 1. Install everything
uv sync --extra pydantic-ai --extra dev

# 2. Configure your model provider
cp .env.example .env
# edit .env — see "Model providers" below

# 3. Seed the test database
uv run python scripts/seed_db.py

# 4. Open the interactive notebook
uv run jupyter lab notebooks/explore.ipynb
```

---

## Benchmark Script

Use the helper script to run setup + benchmark commands in one place:

```bash
# show script usage
./scripts/run_benchmark.sh --help

# list harnesses / architectures / tasks
./scripts/run_benchmark.sh list

# run one benchmark combination
./scripts/run_benchmark.sh run \
  --harness pydantic-ai \
  --architecture enterprise-react \
  --task adi-function-analysis

# run all architectures for one task
./scripts/run_benchmark.sh run-all \
  --harness pydantic-ai \
  --task adi-top-modules

# custom JSON report path
./scripts/run_benchmark.sh run-all \
  --harness pydantic-ai \
  --task adi-top-modules \
  --output reports/my-report.json
```

Useful flags:

- `--skip-setup` skips dependency install and `.env` creation checks.
- `--skip-seed` skips database seeding.
- `--output` sets JSON report path (otherwise a timestamped file is created in `reports/`).
- `--ground-truth` sets ground-truth JSON path used for scoring.
- `--score-output` sets scored JSON output path.
- `--skip-score` skips scoring (default behavior is to score).

By default, the script now produces:
- a raw benchmark report JSON (`--output`),
- a ground-truth JSON (`--ground-truth`),
- a scored report JSON (`--score-output` or `<report>_scored.json`).

---

## Ground Truth Dataset

Generate deterministic task ground truth from the seeded SQLite data:

```bash
uv run python scripts/generate_ground_truth.py
# writes: reports/ground-truth.json
```

Custom output path:

```bash
uv run python scripts/generate_ground_truth.py --output reports/ground-truth-v1.json
```

The JSON includes expected answers for each benchmark task so you can compute:
- correctness (match against expected fields/rows),
- groundedness (claims traceable to DB-backed expected facts),
- hallucination rate (claims not supported by expected facts).

`hn-research` is marked external-dynamic and excluded from strict deterministic scoring.

Score any benchmark report against ground truth:

```bash
uv run python scripts/score_report.py \
  --report reports/run-all.json \
  --ground-truth reports/ground-truth.json \
  --output reports/run-all_scored.json
```

---

## Model providers

Edit `.env` to pick one:

### Cloud — Anthropic
```ini
ANTHROPIC_API_KEY=sk-ant-...
AGENT_BENCH_MODEL=anthropic:claude-sonnet-4-6
```

### Cloud — OpenAI
```ini
OPENAI_API_KEY=sk-...
AGENT_BENCH_MODEL=openai:gpt-4o
```

### Langfuse (required observability)
```ini
LANGFUSE_PUBLIC_KEY=pk-lf-...
LANGFUSE_SECRET_KEY=sk-lf-...
# Either name is accepted:
# LANGFUSE_BASE_URL=https://cloud.langfuse.com
LANGFUSE_HOST=https://cloud.langfuse.com
LANGFUSE_DETAILED_TRACING=true
LANGFUSE_FLUSH_EACH_RUN=false
LANGFUSE_TRACE_SAMPLE_RATE=1.0
```

Benchmark runs require Langfuse. Configure `LANGFUSE_PUBLIC_KEY` and `LANGFUSE_SECRET_KEY`; each run is traced with harness + architecture metadata.
If response time matters, set `LANGFUSE_DETAILED_TRACING=false` and keep `LANGFUSE_FLUSH_EACH_RUN=false`.

### Local — LM Studio (or any OpenAI-compatible server)
```ini
AGENT_BENCH_LOCAL_BASE_URL=http://192.168.68.60:1234/v1
AGENT_BENCH_LOCAL_API_KEY=lm-studio
AGENT_BENCH_MODEL=local:<model-name-exactly-as-shown-in-lm-studio>
```

The `local:` prefix tells the runner to create an `OpenAIChatModel` pointed at your local server instead of calling a cloud provider. LM Studio, Ollama, llama.cpp, and any other OpenAI-compatible endpoint all work this way.

---

## Notebook

`notebooks/explore.ipynb` is the primary interactive interface.

| Section | What it does |
|---|---|
| 1 · Plain chat | Talk to the model with no tools |
| 2 · Multi-turn | Continue a conversation using `message_history` |
| 3 · Enterprise agent | Agent with all 16 database tools wired up |
| 4 · Inspect tool calls | See exactly which tools fired and what they returned |
| 5 · Raw SQL | Write SQLite queries; results rendered as a pandas DataFrame + chart |
| 6 · Quick benchmark | Run the same question through ReAct vs CodeMode and compare elapsed time |

---

## CLI

```bash
# List all harnesses, architectures, and tasks
uv run agent-bench list

# Run one combination
uv run agent-bench run \
  --harness pydantic-ai \
  --architecture enterprise-react \
  --task adi-function-analysis \
  --output reports/single-run.json

# Run every architecture against one task
uv run agent-bench run-all \
  --harness pydantic-ai \
  --task adi-top-modules \
  --output reports/run-all.json
```

---

## Architectures (pydantic-ai)

### Generic

| Name | Description |
|---|---|
| `minimal` | Plain agent, no tools, no harness capabilities |
| `codemode` | CodeMode — wraps tools in a Monty-sandboxed `run_code` call |
| `codemode-mcp-search` | CodeMode + Hacker News MCP + DuckDuckGo web search |

### Enterprise Decision Intelligence benchmark

These six architectures all answer the same tasks against the same SQLite database, making them directly comparable.

| Name | Tools registered via | CodeMode batching |
|---|---|---|
| `enterprise-react` | Direct function registration | No — classic ReAct |
| `enterprise-codemode` | Direct function registration | Yes — harness style |
| `enterprise-mcp-react` | Local FastMCP server | No — classic ReAct |
| `enterprise-mcp-codemode` | Local FastMCP server | Yes — harness style |
| `enterprise-sql-react` | SQL tools only | No — model writes all queries |
| `enterprise-sql-codemode` | SQL tools only | Yes — schema discovery + queries in one sandbox |

**What you can measure across them:**
- Number of LLM round-trips for the same task
- Total elapsed time
- Output correctness

### Exploratory (new orchestration axes, same 17 tools)

| Name | Tools registered via | What's different |
|---|---|---|
| `enterprise-react-toolsearch` | Direct, `defer_loading=True` | [`ToolSearch`](https://ai.pydantic.dev) discovers tools on demand instead of sending all 17 schemas up front |
| `enterprise-codemode-toolsearch` | Direct, `defer_loading=True` | Same on-demand discovery, then batched into `run_code` like `enterprise-codemode` |
| `enterprise-mcp-react-native` | Local FastMCP server, `native=True` | The model **provider** calls the MCP server directly instead of pydantic-ai proxying locally — requires `ENTERPRISE_MCP_PUBLIC_URL` (see below) |
| `enterprise-react-thinking` | Direct function registration | Extended thinking enabled before each tool call |
| `enterprise-codemode-thinking` | Direct function registration | Extended thinking enabled before the sandboxed `run_code` call |

**Native MCP requires a public URL.** Unlike `enterprise-mcp-react`/`enterprise-mcp-codemode` (where pydantic-ai proxies MCP calls locally against the in-process `FastMCP` server), native MCP tool calls are made server-side by the model provider itself — the provider's servers connect directly to the MCP endpoint, so `localhost` is unreachable. Run the server with a streamable-HTTP transport behind a public tunnel (e.g. `ngrok http 8000`) and set `ENTERPRISE_MCP_PUBLIC_URL` in `.env`. There is no `enterprise-mcp-codemode-native`: native MCP tool calls are executed by the provider, never as local pydantic-ai function tools, so there's nothing for CodeMode to batch into a sandboxed `run_code` call.

**Thinking variants drop the `temperature=0` pin.** Anthropic's extended thinking (and most reasoning-effort APIs) reject a pinned temperature, so `enterprise-react-thinking`/`enterprise-codemode-thinking` fall back to the provider's own sampling behavior — expect somewhat more run-to-run variance than the other architectures.

**A note on run-to-run stability:** every architecture is built with `model_settings={"temperature": 0}` (see `runners.py`) to minimize output variance, and CodeMode's `run_code` retry budget is raised from its library default of 3 to 6 so an unlucky generation streak is less likely to exhaust retries and fail the whole run. Neither eliminates variance entirely — per pydantic-ai's own docs, `temperature=0` does not guarantee fully deterministic output, and `seed` is only honored by OpenAI/Groq/Cohere/Mistral/Gemini/xAI, not Anthropic (the default `agent_bench_model`). Use `agent-bench run --repeat N` / `run-all --repeat N` to directly measure how much a given architecture's answers vary across repeated runs of the same task — the scored report includes an `ok_rate`, `distinct_outputs`, and `score_stdev` per architecture.

---

## Test database

A SQLite enterprise Decision Intelligence database lives at `data/enterprise.db` after seeding.

| Table | Rows | Description |
|---|---|---|
| `categories` | 5 | Business functions: Finance, Supply Chain, Sales & Marketing, R&D, HR & People |
| `products` | 50 | Analytics modules across all business functions |
| `customers` | 200 | Enterprise users with engagement tiers (standard / silver / gold) |
| `orders` | 600 | Subscriptions spanning the last year |
| `order_items` | ~1 500 | Line items linking subscriptions to analytics modules |
| `reviews` | ~170 | User satisfaction ratings with 1–5 star scores |

```bash
# Re-seed from scratch at any time
uv run python scripts/seed_db.py --reset
```

### Tools

**Semantic tools** (`src/agent_harness/tools/enterprise.py`) — typed functions a harness agent uses:

| Function | What it does |
|---|---|
| `list_categories()` | All business function categories |
| `search_products(query, category, max_price, in_stock_only)` | Filtered analytics module search |
| `get_product(product_id)` | Module detail with average user rating |
| `get_product_reviews(product_id)` | Recent user satisfaction ratings |
| `get_top_selling_products(limit, days)` | Most-subscribed modules by activation count |
| `get_low_stock_products(threshold)` | Low adoption alert |
| `get_customer(customer_id)` | Business user profile + lifetime subscription stats |
| `search_customers(name, email, tier, city)` | Enterprise user search |
| `get_customer_orders(customer_id)` | Subscription history |
| `get_customer_lifetime_value(customer_id)` | Spend, subscription count, top business function |
| `get_order(order_id)` | Subscription header + analytics modules |
| `get_sales_summary(start_date, end_date)` | Revenue, activations, AOV for a date range |
| `get_revenue_by_month(year)` | Monthly subscription revenue breakdown |

**SQL tools** (`src/agent_harness/tools/sql.py`) — the raw escape hatch a ReAct agent tends to reach for:

| Function | What it does |
|---|---|
| `get_schema_context()` | Full semantic layer: table meanings, relationships, metric patterns, and query tips |
| `list_tables()` | All tables with column signatures |
| `describe_table(table_name)` | Full column definitions |
| `execute_sql(query, limit)` | Read-only SELECT, results capped at `limit` rows |

The full enterprise architectures get all 17 tools. The SQL-only architectures intentionally expose
only `list_tables`, `describe_table`, and `execute_sql`.

### MCP server

All 17 tools are also exposed over the [MCP protocol](https://modelcontextprotocol.io/) via FastMCP:

```bash
# Run the server standalone (stdio transport)
uv run python -m agent_harness.mcp_server

# Run over HTTP (streamable-http, on :8000/mcp) — needed for enterprise-mcp-react-native.
# Put this behind a public tunnel (e.g. `ngrok http 8000`) and set ENTERPRISE_MCP_PUBLIC_URL
# to the tunnel's /mcp URL, since native MCP calls are made server-side by the provider.
uv run python -m agent_harness.mcp_server --http
```

Connect any MCP-compatible client to it, or use it as an in-process capability in pydantic-ai:

```python
from agent_harness.mcp_server import mcp
from pydantic_ai.capabilities import MCP
agent = Agent(model, capabilities=[MCP(mcp)])
```

---

## Tasks

Tasks are shared prompts used across all harnesses and architectures.

### Generic

| Name | Tests |
|---|---|
| `hello` | Basic arithmetic, no tools needed |
| `reasoning` | Multi-step logical deduction |
| `hn-research` | Web search + summarisation |

### Enterprise Decision Intelligence — single lookup

| Name | Tests |
|---|---|
| `adi-top-modules` | Single `get_top_selling_products` call |
| `adi-low-adoption` | Single `get_low_stock_products` call |
| `adi-user-lookup` | `get_customer` + `get_customer_orders` |

### Enterprise Decision Intelligence — multi-step join reasoning

| Name | Tests |
|---|---|
| `adi-function-analysis` | Revenue + unique users + best module per business function |
| `adi-executive-users` | Gold tier profile + best subscription + city aggregation |
| `adi-module-ratings` | Best and worst rated modules with sample review |
| `adi-monthly-trend` | Monthly revenue trend + MoM growth calculation |

### Enterprise Decision Intelligence — complex analytical

| Name | Tests |
|---|---|
| `adi-disengagement-risk` | Multi-condition filter: active then gone quiet |
| `adi-portfolio-depth` | Aggregation grouped by user engagement tier |

### Enterprise architecture routing

`src/agent_harness/tasks/routing_benchmark.py` defines a diagnostic routing benchmark for
choosing among all seven `pydantic-ai` architectures (`minimal` plus the six enterprise
architectures). It includes 12-15 labeled questions per architecture, ground-truth routing
explanations, alternatives, observable routing signals, and an analysis section with
decision-boundary rules for:

- `minimal` (no tools) vs any of the six data-tool architectures
- `enterprise-react` vs `enterprise-codemode`
- `enterprise-mcp-react` vs `enterprise-mcp-codemode`
- `enterprise-sql-react` vs `enterprise-sql-codemode`
- direct typed tools vs local FastMCP tools
- full enterprise tools vs SQL-only tools

The `minimal-*` tasks are fully self-contained (arithmetic, text transformation, logic puzzles,
plus a few greeting/FAQ-style conversational prompts) so a plain, tool-less agent answers them in
one turn with no wasted tool-selection reasoning — none of the six enterprise architectures has
any advantage on these, since the question never touches the database. The three conversational
tasks (`minimal-greeting-*`, `minimal-faq-capabilities`) use `type: "conversational"` in ground
truth: there's no single correct reply to a greeting, so — like `hn-research`'s
`external-dynamic` type — they're intentionally excluded from strict deterministic scoring in
`scripts/score_report.py`.

Use `ROUTING_BENCHMARK` when building an automatic router; it is intentionally separate from the
deterministic answer ground truth because the target label is the architecture choice, not the
final numeric answer.

---

## Project layout

```
src/agent_harness/
  config.py               # Settings from .env; build_pydantic_ai_model()
  registry.py             # Harness / architecture / task registry
  mcp_server.py           # FastMCP server exposing all enterprise Decision Intelligence tools
  runners/
    base.py               # AgentRunner ABC + RunResult dataclass
  harnesses/
    pydantic_ai/
      runners.py          # All architecture builders + PydanticAIRunner
  tools/
    enterprise.py         # 13 semantic tool functions
    sql.py                # list_tables, describe_table, execute_sql, get_schema_context
  tasks/
    builtins.py           # All benchmark prompts
    routing_benchmark.py  # Architecture routing benchmark + decision-boundary analysis
  db/
    schema.py             # SQLite DDL + get_connection() + init_db()
    seed.py               # Deterministic fake-data generator

notebooks/
  explore.ipynb           # Interactive notebook

scripts/
  seed_db.py              # CLI: seed or reset the database

data/
  enterprise.db           # Generated — not committed to git

examples/
  pydantic_ai_quickstart.py
```

---

## Adding a new harness

1. Create `src/agent_harness/harnesses/<name>/`.
2. Implement a class that subclasses `AgentRunner` from `runners/base.py`.
3. Register it in `registry.py` following the `HarnessSpec` pattern.
4. Add any new dependencies as an optional extra in `pyproject.toml`.

## Adding a new task

Add an entry to `TASKS` in `src/agent_harness/tasks/builtins.py`. The key becomes the `--task` flag value in the CLI.

## Development

```bash
uv run pytest          # run tests
uv run ruff check src  # lint
uv run ruff format src # format
```
