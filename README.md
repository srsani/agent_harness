# Agent Harness Bench

Compare **agent harnesses** (capability libraries) against **agentic architectures** (orchestration patterns) using shared tasks and a realistic test database.

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
| 3 · E-commerce agent | Agent with all 16 database tools wired up |
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
  --architecture ecommerce-react \
  --task ec-category-analysis

# Run every architecture against one task
uv run agent-bench run-all --harness pydantic-ai --task ec-top-products
```

---

## Architectures (pydantic-ai)

### Generic

| Name | Description |
|---|---|
| `minimal` | Plain agent, no tools, no harness capabilities |
| `codemode` | CodeMode — wraps tools in a Monty-sandboxed `run_code` call |
| `codemode-mcp-search` | CodeMode + Hacker News MCP + DuckDuckGo web search |

### E-commerce benchmark

These four architectures all answer the same tasks against the same SQLite database, making them directly comparable.

| Name | Tools registered via | CodeMode batching |
|---|---|---|
| `ecommerce-react` | Direct function registration | No — classic ReAct |
| `ecommerce-codemode` | Direct function registration | Yes — harness style |
| `ecommerce-mcp-react` | Local FastMCP server | No — classic ReAct |
| `ecommerce-mcp-codemode` | Local FastMCP server | Yes — harness style |

**What you can measure across them:**
- Number of LLM round-trips for the same task
- Total elapsed time
- Output correctness

---

## Test database

A SQLite e-commerce database lives at `data/ecommerce.db` after seeding.

| Table | Rows | Description |
|---|---|---|
| `categories` | 5 | Product categories |
| `products` | 50 | Items across all categories |
| `customers` | 200 | Customers with tiers (standard / silver / gold) |
| `orders` | 600 | Orders spanning the last year |
| `order_items` | ~1 500 | Line items linking orders to products |
| `reviews` | ~170 | Customer reviews with 1–5 star ratings |

```bash
# Re-seed from scratch at any time
uv run python scripts/seed_db.py --reset
```

### Tools

**Semantic tools** (`src/agent_harness/tools/ecommerce.py`) — typed functions a harness agent uses:

| Function | What it does |
|---|---|
| `list_categories()` | All product categories |
| `search_products(query, category, max_price, in_stock_only)` | Filtered product search |
| `get_product(product_id)` | Product detail with average rating |
| `get_product_reviews(product_id)` | Recent reviews |
| `get_top_selling_products(limit, days)` | Best sellers by units sold |
| `get_low_stock_products(threshold)` | Inventory alert |
| `get_customer(customer_id)` | Profile + lifetime order stats |
| `search_customers(name, email, tier, city)` | Customer search |
| `get_customer_orders(customer_id)` | Order history |
| `get_customer_lifetime_value(customer_id)` | Spend, order count, favourite category |
| `get_order(order_id)` | Order header + line items |
| `get_sales_summary(start_date, end_date)` | Revenue, orders, AOV for a date range |
| `get_revenue_by_month(year)` | Monthly revenue breakdown |

**SQL tools** (`src/agent_harness/tools/sql.py`) — the raw escape hatch a ReAct agent tends to reach for:

| Function | What it does |
|---|---|
| `list_tables()` | All tables with column signatures |
| `describe_table(table_name)` | Full column definitions |
| `execute_sql(query, limit)` | Read-only SELECT, results capped at `limit` rows |

### MCP server

All 16 tools are also exposed over the [MCP protocol](https://modelcontextprotocol.io/) via FastMCP:

```bash
# Run the server standalone (stdio transport)
uv run python -m agent_harness.mcp_server
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

### E-commerce — single lookup

| Name | Tests |
|---|---|
| `ec-top-products` | Single `get_top_selling_products` call |
| `ec-low-stock` | Single `get_low_stock_products` call |
| `ec-customer-lookup` | `get_customer` + `get_customer_orders` |

### E-commerce — multi-step join reasoning

| Name | Tests |
|---|---|
| `ec-category-analysis` | Revenue + unique buyers + best product per category |
| `ec-gold-customers` | Gold tier profile + best order + city aggregation |
| `ec-review-insights` | Best and worst reviewed products with sample reviews |
| `ec-monthly-trend` | Monthly revenue trend + MoM growth calculation |

### E-commerce — complex analytical

| Name | Tests |
|---|---|
| `ec-churn-risk` | Multi-condition filter: active then gone quiet |
| `ec-basket-size` | Aggregation grouped by customer tier |

---

## Project layout

```
src/agent_harness/
  config.py               # Settings from .env; build_pydantic_ai_model()
  registry.py             # Harness / architecture / task registry
  mcp_server.py           # FastMCP server exposing all e-commerce tools
  runners/
    base.py               # AgentRunner ABC + RunResult dataclass
  harnesses/
    pydantic_ai/
      runners.py          # All architecture builders + PydanticAIRunner
  tools/
    ecommerce.py          # 13 semantic tool functions
    sql.py                # list_tables, describe_table, execute_sql
  tasks/
    builtins.py           # All benchmark prompts
  db/
    schema.py             # SQLite DDL + get_connection() + init_db()
    seed.py               # Deterministic fake-data generator

notebooks/
  explore.ipynb           # Interactive notebook

scripts/
  seed_db.py              # CLI: seed or reset the database

data/
  ecommerce.db            # Generated — not committed to git

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
