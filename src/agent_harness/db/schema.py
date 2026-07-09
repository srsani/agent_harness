"""SQLite schema, connection helpers, and semantic metadata for the enterprise Decision Intelligence database."""

from __future__ import annotations

import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).resolve().parents[4] / "data" / "enterprise.db"

DDL = """
CREATE TABLE IF NOT EXISTS categories (
    id          INTEGER PRIMARY KEY,
    -- Business function name: Finance | Supply Chain | Sales & Marketing | R&D | HR & People
    name        TEXT    NOT NULL UNIQUE,
    -- Plain-English scope description for the business function
    description TEXT    NOT NULL
);

CREATE TABLE IF NOT EXISTS products (
    id                   INTEGER PRIMARY KEY,
    category_id          INTEGER NOT NULL REFERENCES categories(id),
    -- Full name of the analytics module
    name                 TEXT    NOT NULL,
    -- One-sentence description of what the module does
    description          TEXT    NOT NULL,
    -- Annual license cost per seat in USD
    annual_license_usd   REAL    NOT NULL CHECK(annual_license_usd > 0),
    -- Current number of active team/site deployments of this module
    active_deployments   INTEGER NOT NULL DEFAULT 0,
    -- ISO-8601 date the module was first listed
    created_at           TEXT    NOT NULL
);

CREATE TABLE IF NOT EXISTS customers (
    id         INTEGER PRIMARY KEY,
    email      TEXT NOT NULL UNIQUE,
    full_name  TEXT NOT NULL,
    city       TEXT NOT NULL,
    -- Two-letter ISO country code: US, GB, DE, FR, CA, AU
    country    TEXT NOT NULL,
    -- Engagement tier: standard=analyst/IC  silver=manager  gold=director/VP/C-suite
    tier       TEXT NOT NULL DEFAULT 'standard' CHECK(tier IN ('standard','silver','gold')),
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS orders (
    id           INTEGER PRIMARY KEY,
    customer_id  INTEGER NOT NULL REFERENCES customers(id),
    -- Lifecycle: pending → shipped (access provisioned) → delivered (fully active) | cancelled
    status       TEXT    NOT NULL CHECK(status IN ('pending','shipped','delivered','cancelled')),
    -- Total contract value in USD (sum of all line items: seats × unit_price)
    total_amount REAL    NOT NULL,
    created_at   TEXT    NOT NULL,
    -- NULL for pending/cancelled; populated when access is provisioned
    shipped_at   TEXT
);

CREATE TABLE IF NOT EXISTS order_items (
    id         INTEGER PRIMARY KEY,
    order_id   INTEGER NOT NULL REFERENCES orders(id),
    product_id INTEGER NOT NULL REFERENCES products(id),
    -- Number of licence seats purchased for this module in this subscription
    seats      INTEGER NOT NULL CHECK(seats > 0),
    -- Per-seat annual price locked at subscription time
    unit_price REAL    NOT NULL CHECK(unit_price > 0)
);

CREATE TABLE IF NOT EXISTS reviews (
    id          INTEGER PRIMARY KEY,
    product_id  INTEGER NOT NULL REFERENCES products(id),
    customer_id INTEGER NOT NULL REFERENCES customers(id),
    -- 1–5 integer star rating (5 = highest satisfaction)
    rating      INTEGER NOT NULL CHECK(rating BETWEEN 1 AND 5),
    title       TEXT    NOT NULL,
    body        TEXT    NOT NULL,
    -- Submitted 5–60 days after subscription delivery
    created_at  TEXT    NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_products_category   ON products(category_id);
CREATE INDEX IF NOT EXISTS idx_orders_customer     ON orders(customer_id);
CREATE INDEX IF NOT EXISTS idx_order_items_order   ON order_items(order_id);
CREATE INDEX IF NOT EXISTS idx_order_items_product ON order_items(product_id);
CREATE INDEX IF NOT EXISTS idx_reviews_product     ON reviews(product_id);
CREATE INDEX IF NOT EXISTS idx_reviews_customer    ON reviews(customer_id);

-- ── Support & Success ─────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS support_agents (
    id         INTEGER PRIMARY KEY,
    full_name  TEXT    NOT NULL,
    -- Region the agent primarily supports: US, EMEA, APAC
    region     TEXT    NOT NULL CHECK(region IN ('US','EMEA','APAC')),
    hired_at   TEXT    NOT NULL
);

CREATE TABLE IF NOT EXISTS support_tickets (
    id                  INTEGER PRIMARY KEY,
    customer_id         INTEGER NOT NULL REFERENCES customers(id),
    product_id          INTEGER NOT NULL REFERENCES products(id),
    agent_id            INTEGER NOT NULL REFERENCES support_agents(id),
    subject             TEXT    NOT NULL,
    -- low | medium | high | urgent
    priority            TEXT    NOT NULL CHECK(priority IN ('low','medium','high','urgent')),
    -- open | pending | resolved | closed
    status              TEXT    NOT NULL CHECK(status IN ('open','pending','resolved','closed')),
    created_at          TEXT    NOT NULL,
    -- NULL until status is resolved/closed
    resolved_at         TEXT,
    -- 1-5 post-resolution satisfaction score; NULL if unresolved or not rated
    satisfaction_rating INTEGER CHECK(satisfaction_rating BETWEEN 1 AND 5)
);

-- ── Marketing Campaigns ────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS campaigns (
    id          INTEGER PRIMARY KEY,
    name        TEXT    NOT NULL,
    -- email | paid_search | social | webinar | content | events
    channel     TEXT    NOT NULL CHECK(channel IN ('email','paid_search','social','webinar','content','events')),
    -- planned | active | completed | paused
    status      TEXT    NOT NULL CHECK(status IN ('planned','active','completed','paused')),
    budget_usd  REAL    NOT NULL CHECK(budget_usd > 0),
    start_date  TEXT    NOT NULL,
    end_date    TEXT    NOT NULL
);

CREATE TABLE IF NOT EXISTS campaign_performance (
    id           INTEGER PRIMARY KEY,
    campaign_id  INTEGER NOT NULL REFERENCES campaigns(id),
    -- Calendar month this performance snapshot covers, format YYYY-MM
    month        TEXT    NOT NULL,
    impressions  INTEGER NOT NULL DEFAULT 0,
    clicks       INTEGER NOT NULL DEFAULT 0,
    leads        INTEGER NOT NULL DEFAULT 0,
    conversions  INTEGER NOT NULL DEFAULT 0,
    spend_usd    REAL    NOT NULL DEFAULT 0
);

-- ── Procurement / Suppliers ────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS suppliers (
    id          INTEGER PRIMARY KEY,
    name        TEXT    NOT NULL,
    country     TEXT    NOT NULL,
    -- Sourcing category: raw_materials | logistics | software | facilities | professional_services
    category    TEXT    NOT NULL CHECK(category IN ('raw_materials','logistics','software','facilities','professional_services')),
    -- 1-5 supplier scorecard rating (5 = best)
    rating      REAL    NOT NULL CHECK(rating BETWEEN 1 AND 5),
    created_at  TEXT    NOT NULL
);

CREATE TABLE IF NOT EXISTS purchase_orders (
    id            INTEGER PRIMARY KEY,
    supplier_id   INTEGER NOT NULL REFERENCES suppliers(id),
    -- draft | approved | shipped | received | cancelled
    status        TEXT    NOT NULL CHECK(status IN ('draft','approved','shipped','received','cancelled')),
    total_amount  REAL    NOT NULL,
    ordered_at    TEXT    NOT NULL,
    expected_at   TEXT    NOT NULL,
    -- NULL until status = received; compare to expected_at for lateness
    received_at   TEXT
);

-- ── Workforce / HR ──────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS departments (
    id           INTEGER PRIMARY KEY,
    name         TEXT    NOT NULL UNIQUE,
    -- Maps to a categories.name business function this department primarily serves
    function     TEXT    NOT NULL,
    budget_usd   REAL    NOT NULL
);

CREATE TABLE IF NOT EXISTS employees (
    id             INTEGER PRIMARY KEY,
    department_id  INTEGER NOT NULL REFERENCES departments(id),
    full_name      TEXT    NOT NULL,
    title          TEXT    NOT NULL,
    hired_at       TEXT    NOT NULL,
    salary_usd     REAL    NOT NULL,
    -- Self-referencing FK; NULL for department heads with no manager
    manager_id     INTEGER REFERENCES employees(id),
    -- 0 once the employee has left the company (attrition)
    is_active      INTEGER NOT NULL DEFAULT 1 CHECK(is_active IN (0,1)),
    -- NULL while is_active = 1
    departed_at    TEXT
);

CREATE TABLE IF NOT EXISTS performance_reviews (
    id           INTEGER PRIMARY KEY,
    employee_id  INTEGER NOT NULL REFERENCES employees(id),
    review_date  TEXT    NOT NULL,
    -- 1-5 performance rating (5 = highest)
    rating       INTEGER NOT NULL CHECK(rating BETWEEN 1 AND 5),
    summary      TEXT    NOT NULL
);

-- ── Finance / Budgets ────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS budgets (
    id             INTEGER PRIMARY KEY,
    department_id  INTEGER NOT NULL REFERENCES departments(id),
    year           INTEGER NOT NULL,
    -- opex | capex | headcount | travel | marketing_spend
    category       TEXT    NOT NULL CHECK(category IN ('opex','capex','headcount','travel','marketing_spend')),
    allocated_usd  REAL    NOT NULL
);

CREATE TABLE IF NOT EXISTS expenses (
    id             INTEGER PRIMARY KEY,
    budget_id      INTEGER NOT NULL REFERENCES budgets(id),
    department_id  INTEGER NOT NULL REFERENCES departments(id),
    category       TEXT    NOT NULL CHECK(category IN ('opex','capex','headcount','travel','marketing_spend')),
    amount_usd     REAL    NOT NULL CHECK(amount_usd > 0),
    incurred_at    TEXT    NOT NULL,
    description    TEXT    NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_tickets_customer       ON support_tickets(customer_id);
CREATE INDEX IF NOT EXISTS idx_tickets_agent          ON support_tickets(agent_id);
CREATE INDEX IF NOT EXISTS idx_tickets_product        ON support_tickets(product_id);
CREATE INDEX IF NOT EXISTS idx_campaign_perf_campaign  ON campaign_performance(campaign_id);
CREATE INDEX IF NOT EXISTS idx_po_supplier            ON purchase_orders(supplier_id);
CREATE INDEX IF NOT EXISTS idx_employees_department   ON employees(department_id);
CREATE INDEX IF NOT EXISTS idx_employees_manager      ON employees(manager_id);
CREATE INDEX IF NOT EXISTS idx_reviews_employee        ON performance_reviews(employee_id);
CREATE INDEX IF NOT EXISTS idx_budgets_department      ON budgets(department_id);
CREATE INDEX IF NOT EXISTS idx_expenses_budget         ON expenses(budget_id);
CREATE INDEX IF NOT EXISTS idx_expenses_department     ON expenses(department_id);
"""

# ── Semantic metadata ─────────────────────────────────────────────────────────
# Used by list_tables(), describe_table(), and get_schema_context() to surface
# domain meaning alongside raw SQL schema — the foundation of the semantic layer.

SCHEMA_METADATA: dict[str, dict] = {
    "categories": {
        "semantic_name": "Business Functions",
        "description": (
            "The five enterprise business domains that analytics modules are grouped under. "
            "Every module belongs to exactly one business function. "
            "Values: Finance, Supply Chain, Sales & Marketing, "
            "Research & Development, HR & People."
        ),
        "columns": {
            "id": "Surrogate primary key.",
            "name": (
                "Business function name. "
                "One of: Finance, Supply Chain, Sales & Marketing, "
                "Research & Development, HR & People."
            ),
            "description": "Plain-English scope description for the business function.",
        },
    },
    "products": {
        "semantic_name": "Analytics Modules",
        "description": (
            "Each row is a licensed AI/ML analytics module that enterprise users can subscribe to. "
            "Modules are grouped by business function (categories). "
            "annual_license_usd is the per-seat annual cost in USD. "
            "active_deployments is the current number of teams / sites running this module. "
            "~50 modules across the 5 business functions."
        ),
        "columns": {
            "id": "Surrogate primary key.",
            "category_id": "FK → categories.id — the owning business function.",
            "name": "Full module name (e.g. 'Revenue Forecast Model').",
            "description": "One-sentence summary of what the module does.",
            "annual_license_usd": (
                "Annual per-seat license cost in USD. Range: $5,500–$18,000."
            ),
            "active_deployments": (
                "Current number of active team / site deployments. "
                "Low values signal low adoption. Range: 18–140."
            ),
            "created_at": "ISO-8601 date the module was first listed in the catalogue.",
        },
    },
    "customers": {
        "semantic_name": "Enterprise Users",
        "description": (
            "Enterprise professionals who subscribe to analytics modules. "
            "Segmented by engagement tier: "
            "standard (analyst/IC), silver (manager/senior IC), gold (director/VP/C-suite). "
            "~200 users across 17 cities in US, UK, DE, FR, CA, AU."
        ),
        "columns": {
            "id": "Surrogate primary key.",
            "email": "Unique work email address.",
            "full_name": "First and last name.",
            "city": "Primary office city.",
            "country": "Two-letter ISO country code (US, GB, DE, FR, CA, AU).",
            "tier": (
                "Engagement tier. "
                "standard = analyst / individual contributor, "
                "silver = manager / senior IC, "
                "gold = director / VP / C-suite."
            ),
            "created_at": "ISO-8601 timestamp when the account was created.",
        },
    },
    "orders": {
        "semantic_name": "Subscriptions",
        "description": (
            "A subscription is a purchase event: one enterprise user activates one or more "
            "analytics modules. Each order links a customer to products via order_items. "
            "Status lifecycle: pending → shipped (access provisioned) → delivered (fully active) "
            "| cancelled. "
            "~600 subscriptions spanning the last year. "
            "total_amount = SUM(order_items.seats × order_items.unit_price) for that order."
        ),
        "columns": {
            "id": "Surrogate primary key.",
            "customer_id": "FK → customers.id.",
            "status": (
                "Lifecycle status. "
                "pending = awaiting provisioning, "
                "shipped = access provisioned, "
                "delivered = fully active and in use, "
                "cancelled = subscription cancelled."
            ),
            "total_amount": (
                "Total contract value in USD "
                "(sum of seats × unit_price across all line items)."
            ),
            "created_at": "ISO-8601 timestamp when the subscription was placed.",
            "shipped_at": (
                "ISO-8601 timestamp when access was provisioned. "
                "NULL for pending and cancelled subscriptions."
            ),
        },
    },
    "order_items": {
        "semantic_name": "Subscription Line Items",
        "description": (
            "Each row is one analytics module included in a subscription, "
            "with the number of licence seats and the per-seat price locked at subscription time. "
            "Revenue contribution = seats × unit_price. "
            "Join to orders for subscription status; join to products for module details. "
            "~1,500 line items total."
        ),
        "columns": {
            "id": "Surrogate primary key.",
            "order_id": "FK → orders.id.",
            "product_id": "FK → products.id — the subscribed analytics module.",
            "seats": (
                "Number of licence seats purchased for this module in this subscription. "
                "Range 1–3."
            ),
            "unit_price": (
                "Per-seat annual price locked at subscription time "
                "(may differ from current products.annual_license_usd)."
            ),
        },
    },
    "reviews": {
        "semantic_name": "User Satisfaction Ratings",
        "description": (
            "Post-deployment satisfaction ratings for analytics modules. "
            "Only users with a delivered subscription can submit a rating. "
            "~25 % of delivered line items generate a review. "
            "Each user can rate a given module at most once. "
            "~170 reviews total."
        ),
        "columns": {
            "id": "Surrogate primary key.",
            "product_id": "FK → products.id — the rated analytics module.",
            "customer_id": "FK → customers.id — the reviewer.",
            "rating": "Integer 1–5 star rating (5 = highest satisfaction).",
            "title": "Short headline for the review.",
            "body": "Full free-text feedback.",
            "created_at": "ISO-8601 timestamp (submitted 5–60 days after delivery).",
        },
    },
    "support_agents": {
        "semantic_name": "Support Agents",
        "description": (
            "Customer support staff who handle tickets, grouped by the region they primarily "
            "support: US, EMEA, APAC."
        ),
        "columns": {
            "id": "Surrogate primary key.",
            "full_name": "Agent's full name.",
            "region": "Primary support region: US, EMEA, or APAC.",
            "hired_at": "ISO-8601 date the agent joined the support team.",
        },
    },
    "support_tickets": {
        "semantic_name": "Support Tickets",
        "description": (
            "Customer support cases raised against a specific analytics module. "
            "Lifecycle: open -> pending -> resolved -> closed. "
            "satisfaction_rating is only populated after resolution and only if the customer rated it."
        ),
        "columns": {
            "id": "Surrogate primary key.",
            "customer_id": "FK -> customers.id — who raised the ticket.",
            "product_id": "FK -> products.id — which analytics module the ticket concerns.",
            "agent_id": "FK -> support_agents.id — who is handling the ticket.",
            "subject": "Short one-line ticket subject.",
            "priority": "low | medium | high | urgent.",
            "status": "open | pending | resolved | closed.",
            "created_at": "ISO-8601 timestamp the ticket was opened.",
            "resolved_at": "ISO-8601 timestamp the ticket was resolved; NULL if still open/pending.",
            "satisfaction_rating": "1-5 post-resolution CSAT score; NULL if unresolved or unrated.",
        },
    },
    "campaigns": {
        "semantic_name": "Marketing Campaigns",
        "description": (
            "Marketing campaigns across channels (email, paid search, social, webinar, content, "
            "events). Each campaign has monthly performance snapshots in campaign_performance."
        ),
        "columns": {
            "id": "Surrogate primary key.",
            "name": "Campaign name.",
            "channel": "email | paid_search | social | webinar | content | events.",
            "status": "planned | active | completed | paused.",
            "budget_usd": "Total planned budget for the campaign in USD.",
            "start_date": "ISO-8601 campaign start date.",
            "end_date": "ISO-8601 campaign end date.",
        },
    },
    "campaign_performance": {
        "semantic_name": "Campaign Monthly Performance",
        "description": (
            "One row per campaign per calendar month it ran, with funnel metrics: "
            "impressions -> clicks -> leads -> conversions, and actual spend that month. "
            "ROI-style metrics should sum spend_usd and conversions across all months for a campaign."
        ),
        "columns": {
            "id": "Surrogate primary key.",
            "campaign_id": "FK -> campaigns.id.",
            "month": "Calendar month this snapshot covers, format YYYY-MM.",
            "impressions": "Ad/email impressions that month.",
            "clicks": "Clicks that month.",
            "leads": "Marketing-qualified leads generated that month.",
            "conversions": "Leads that converted to a paying subscription that month.",
            "spend_usd": "Actual spend that month in USD.",
        },
    },
    "suppliers": {
        "semantic_name": "Suppliers",
        "description": (
            "Third-party suppliers used for procurement, rated on a 1-5 scorecard. "
            "Sourcing categories: raw_materials, logistics, software, facilities, professional_services."
        ),
        "columns": {
            "id": "Surrogate primary key.",
            "name": "Supplier company name.",
            "country": "Two-letter ISO country code.",
            "category": "raw_materials | logistics | software | facilities | professional_services.",
            "rating": "1-5 supplier scorecard rating (5 = best).",
            "created_at": "ISO-8601 date the supplier relationship began.",
        },
    },
    "purchase_orders": {
        "semantic_name": "Purchase Orders",
        "description": (
            "Procurement purchase orders placed with suppliers. Lifecycle: draft -> approved -> "
            "shipped -> received | cancelled. A PO is 'late' when received_at is after expected_at."
        ),
        "columns": {
            "id": "Surrogate primary key.",
            "supplier_id": "FK -> suppliers.id.",
            "status": "draft | approved | shipped | received | cancelled.",
            "total_amount": "Total PO value in USD.",
            "ordered_at": "ISO-8601 timestamp the PO was placed.",
            "expected_at": "ISO-8601 timestamp delivery was expected.",
            "received_at": "ISO-8601 timestamp actually received; NULL until status = received.",
        },
    },
    "departments": {
        "semantic_name": "Departments",
        "description": (
            "Internal company departments. `function` maps to the categories.name business "
            "function the department primarily serves (Finance, Supply Chain, Sales & Marketing, "
            "Research & Development, HR & People)."
        ),
        "columns": {
            "id": "Surrogate primary key.",
            "name": "Department name.",
            "function": "The business function (categories.name) this department serves.",
            "budget_usd": "Total annual operating budget in USD.",
        },
    },
    "employees": {
        "semantic_name": "Employees",
        "description": (
            "Internal company workforce. manager_id self-references employees.id for reporting "
            "lines. is_active=0 marks someone who has left the company (attrition)."
        ),
        "columns": {
            "id": "Surrogate primary key.",
            "department_id": "FK -> departments.id.",
            "full_name": "Employee's full name.",
            "title": "Job title.",
            "hired_at": "ISO-8601 hire date.",
            "salary_usd": "Annual base salary in USD.",
            "manager_id": "FK -> employees.id — direct manager; NULL for department heads.",
            "is_active": "1 = currently employed, 0 = departed (attrition).",
            "departed_at": "ISO-8601 departure date; NULL while is_active = 1.",
        },
    },
    "performance_reviews": {
        "semantic_name": "Employee Performance Reviews",
        "description": "Periodic 1-5 performance ratings for employees, with a short summary.",
        "columns": {
            "id": "Surrogate primary key.",
            "employee_id": "FK -> employees.id.",
            "review_date": "ISO-8601 date of the review.",
            "rating": "1-5 performance rating (5 = highest).",
            "summary": "Short free-text review summary.",
        },
    },
    "budgets": {
        "semantic_name": "Department Budgets",
        "description": (
            "Annual budget allocations per department per category "
            "(opex, capex, headcount, travel, marketing_spend). Compare to expenses for variance."
        ),
        "columns": {
            "id": "Surrogate primary key.",
            "department_id": "FK -> departments.id.",
            "year": "Four-digit budget year.",
            "category": "opex | capex | headcount | travel | marketing_spend.",
            "allocated_usd": "Allocated budget amount in USD for that year/category.",
        },
    },
    "expenses": {
        "semantic_name": "Expenses",
        "description": (
            "Individual expense line items charged against a budget. "
            "Sum of expenses.amount_usd for a budget_id vs. budgets.allocated_usd gives variance."
        ),
        "columns": {
            "id": "Surrogate primary key.",
            "budget_id": "FK -> budgets.id.",
            "department_id": "FK -> departments.id (denormalized for convenience).",
            "category": "opex | capex | headcount | travel | marketing_spend.",
            "amount_usd": "Expense amount in USD.",
            "incurred_at": "ISO-8601 date the expense was incurred.",
            "description": "Short free-text expense description.",
        },
    },
}

# ── Foreign-key relationship map ──────────────────────────────────────────────

RELATIONSHIPS = [
    {"from_table": "products",    "from_col": "category_id",  "to_table": "categories", "to_col": "id"},
    {"from_table": "orders",      "from_col": "customer_id",  "to_table": "customers",  "to_col": "id"},
    {"from_table": "order_items", "from_col": "order_id",     "to_table": "orders",     "to_col": "id"},
    {"from_table": "order_items", "from_col": "product_id",   "to_table": "products",   "to_col": "id"},
    {"from_table": "reviews",     "from_col": "product_id",   "to_table": "products",   "to_col": "id"},
    {"from_table": "reviews",     "from_col": "customer_id",  "to_table": "customers",  "to_col": "id"},
    {"from_table": "support_tickets",      "from_col": "customer_id",    "to_table": "customers",       "to_col": "id"},
    {"from_table": "support_tickets",      "from_col": "product_id",     "to_table": "products",        "to_col": "id"},
    {"from_table": "support_tickets",      "from_col": "agent_id",       "to_table": "support_agents",  "to_col": "id"},
    {"from_table": "campaign_performance", "from_col": "campaign_id",    "to_table": "campaigns",       "to_col": "id"},
    {"from_table": "purchase_orders",      "from_col": "supplier_id",    "to_table": "suppliers",       "to_col": "id"},
    {"from_table": "employees",            "from_col": "department_id",  "to_table": "departments",     "to_col": "id"},
    {"from_table": "employees",            "from_col": "manager_id",     "to_table": "employees",       "to_col": "id"},
    {"from_table": "performance_reviews",  "from_col": "employee_id",    "to_table": "employees",       "to_col": "id"},
    {"from_table": "budgets",              "from_col": "department_id",  "to_table": "departments",     "to_col": "id"},
    {"from_table": "expenses",             "from_col": "budget_id",      "to_table": "budgets",         "to_col": "id"},
    {"from_table": "expenses",             "from_col": "department_id",  "to_table": "departments",     "to_col": "id"},
]

# ── Common business metric patterns ──────────────────────────────────────────
# Maps natural-language metric names to the canonical SQL expression.
# A semantic layer should use these patterns when users ask for these concepts.

BUSINESS_METRICS = {
    "subscription_revenue": (
        "SUM(o.total_amount) FROM orders o WHERE o.status != 'cancelled'"
    ),
    "delivered_revenue": (
        "SUM(o.total_amount) FROM orders o WHERE o.status = 'delivered'"
    ),
    "module_revenue": (
        "SUM(oi.seats * oi.unit_price) FROM order_items oi "
        "JOIN orders o ON o.id = oi.order_id WHERE o.status != 'cancelled'"
    ),
    "user_lifetime_value": (
        "SUM(o.total_amount) per customer WHERE o.status != 'cancelled'"
    ),
    "avg_subscription_value": (
        "AVG(o.total_amount) FROM orders o WHERE o.status != 'cancelled'"
    ),
    "module_avg_rating": (
        "AVG(r.rating) FROM reviews r GROUP BY r.product_id"
    ),
    "active_users_in_period": (
        "COUNT(DISTINCT o.customer_id) FROM orders o "
        "WHERE o.created_at >= <start> AND o.status != 'cancelled'"
    ),
    "module_activation_count": (
        "COUNT(DISTINCT oi.order_id) FROM order_items oi "
        "JOIN orders o ON o.id = oi.order_id WHERE o.status != 'cancelled'"
    ),
    "portfolio_depth": (
        "AVG(item_count) WHERE item_count = "
        "COUNT(oi.id) per order FROM order_items oi GROUP BY oi.order_id"
    ),
    "ticket_resolution_rate": (
        "COUNT(*) WHERE status IN ('resolved','closed') / COUNT(*) FROM support_tickets"
    ),
    "avg_csat": "AVG(satisfaction_rating) FROM support_tickets WHERE satisfaction_rating IS NOT NULL",
    "campaign_roi": (
        "(SUM(cp.conversions) * avg_subscription_value - SUM(cp.spend_usd)) / SUM(cp.spend_usd) "
        "FROM campaign_performance cp WHERE cp.campaign_id = <id>"
    ),
    "conversion_rate": "SUM(cp.conversions) / NULLIF(SUM(cp.leads), 0) FROM campaign_performance cp",
    "supplier_on_time_rate": (
        "COUNT(*) WHERE received_at <= expected_at / COUNT(*) WHERE status = 'received' "
        "FROM purchase_orders"
    ),
    "attrition_rate": (
        "COUNT(*) WHERE is_active = 0 AND departed_at >= <start> / "
        "COUNT(*) WHERE hired_at <= <start> FROM employees"
    ),
    "budget_variance": (
        "budgets.allocated_usd - SUM(expenses.amount_usd) FROM expenses "
        "JOIN budgets ON budgets.id = expenses.budget_id GROUP BY budgets.id"
    ),
}


def get_connection(path: Path | None = None) -> sqlite3.Connection:
    target = path or DB_PATH
    target.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(target)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db(path: Path | None = None) -> None:
    """Create all tables (idempotent)."""
    with get_connection(path) as conn:
        conn.executescript(DDL)
