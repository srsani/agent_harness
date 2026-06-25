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
}

# ── Foreign-key relationship map ──────────────────────────────────────────────

RELATIONSHIPS = [
    {"from_table": "products",    "from_col": "category_id",  "to_table": "categories", "to_col": "id"},
    {"from_table": "orders",      "from_col": "customer_id",  "to_table": "customers",  "to_col": "id"},
    {"from_table": "order_items", "from_col": "order_id",     "to_table": "orders",     "to_col": "id"},
    {"from_table": "order_items", "from_col": "product_id",   "to_table": "products",   "to_col": "id"},
    {"from_table": "reviews",     "from_col": "product_id",   "to_table": "products",   "to_col": "id"},
    {"from_table": "reviews",     "from_col": "customer_id",  "to_table": "customers",  "to_col": "id"},
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
    "portfolio_depth": (
        "AVG(item_count) WHERE item_count = "
        "COUNT(oi.id) per order FROM order_items oi GROUP BY oi.order_id"
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
