"""SQLite schema and connection helpers for the test e-commerce database."""

from __future__ import annotations

import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).resolve().parents[4] / "data" / "ecommerce.db"

DDL = """
CREATE TABLE IF NOT EXISTS categories (
    id          INTEGER PRIMARY KEY,
    name        TEXT    NOT NULL UNIQUE,
    description TEXT    NOT NULL
);

CREATE TABLE IF NOT EXISTS products (
    id             INTEGER PRIMARY KEY,
    category_id    INTEGER NOT NULL REFERENCES categories(id),
    name           TEXT    NOT NULL,
    description    TEXT    NOT NULL,
    price          REAL    NOT NULL CHECK(price > 0),
    stock_quantity INTEGER NOT NULL DEFAULT 0,
    created_at     TEXT    NOT NULL   -- ISO-8601
);

CREATE TABLE IF NOT EXISTS customers (
    id         INTEGER PRIMARY KEY,
    email      TEXT NOT NULL UNIQUE,
    full_name  TEXT NOT NULL,
    city       TEXT NOT NULL,
    country    TEXT NOT NULL,
    tier       TEXT NOT NULL DEFAULT 'standard' CHECK(tier IN ('standard','silver','gold')),
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS orders (
    id           INTEGER PRIMARY KEY,
    customer_id  INTEGER NOT NULL REFERENCES customers(id),
    status       TEXT    NOT NULL CHECK(status IN ('pending','shipped','delivered','cancelled')),
    total_amount REAL    NOT NULL,
    created_at   TEXT    NOT NULL,
    shipped_at   TEXT
);

CREATE TABLE IF NOT EXISTS order_items (
    id          INTEGER PRIMARY KEY,
    order_id    INTEGER NOT NULL REFERENCES orders(id),
    product_id  INTEGER NOT NULL REFERENCES products(id),
    quantity    INTEGER NOT NULL CHECK(quantity > 0),
    unit_price  REAL    NOT NULL CHECK(unit_price > 0)
);

CREATE TABLE IF NOT EXISTS reviews (
    id          INTEGER PRIMARY KEY,
    product_id  INTEGER NOT NULL REFERENCES products(id),
    customer_id INTEGER NOT NULL REFERENCES customers(id),
    rating      INTEGER NOT NULL CHECK(rating BETWEEN 1 AND 5),
    title       TEXT    NOT NULL,
    body        TEXT    NOT NULL,
    created_at  TEXT    NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_products_category   ON products(category_id);
CREATE INDEX IF NOT EXISTS idx_orders_customer     ON orders(customer_id);
CREATE INDEX IF NOT EXISTS idx_order_items_order   ON order_items(order_id);
CREATE INDEX IF NOT EXISTS idx_order_items_product ON order_items(product_id);
CREATE INDEX IF NOT EXISTS idx_reviews_product     ON reviews(product_id);
CREATE INDEX IF NOT EXISTS idx_reviews_customer    ON reviews(customer_id);
"""


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
