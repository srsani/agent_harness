"""Seed the enterprise Decision Intelligence benchmark database.

Usage:
    uv run python scripts/seed_db.py
    uv run python scripts/seed_db.py --reset   # drop and re-create
"""

from __future__ import annotations

import argparse
from pathlib import Path

from agent_harness.db.schema import DB_PATH, get_connection
from agent_harness.db.seed import seed_db


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed the enterprise Decision Intelligence benchmark database.")
    parser.add_argument("--reset", action="store_true", help="Delete existing data before seeding.")
    parser.add_argument("--db", default=None, help="Custom path to the SQLite database file.")
    args = parser.parse_args()

    path = Path(args.db) if args.db else None
    target = path or DB_PATH

    if args.reset and target.exists():
        print(f"Removing existing database at {target}")
        target.unlink()

    print(f"Seeding database at {target} ...")
    seed_db(path)

    # Print quick summary
    with get_connection(path) as conn:
        for table in ("categories", "products", "customers", "orders", "order_items", "reviews"):
            count = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]  # noqa: S608
            print(f"  {table:15s}: {count:>6} rows")

    print("Done.")


if __name__ == "__main__":
    main()
