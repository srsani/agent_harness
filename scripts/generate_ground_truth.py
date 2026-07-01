from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from agent_harness.db.schema import DB_PATH, get_connection
from agent_harness.tasks.builtins import TASKS


def _rows(conn, sql: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
    cur = conn.execute(sql, params)
    cols = [d[0] for d in cur.description] if cur.description else []
    return [dict(zip(cols, row)) for row in cur.fetchall()]


def _row(conn, sql: str, params: tuple[Any, ...] = ()) -> dict[str, Any] | None:
    rows = _rows(conn, sql, params)
    return rows[0] if rows else None


def build_ground_truth() -> dict[str, Any]:
    with get_connection() as conn:
        max_created = _row(conn, "SELECT MAX(created_at) AS max_created FROM orders")
        max_created_at = max_created["max_created"] if max_created else None

        # Last full calendar year in DB (e.g. if latest row is 2026, use 2025).
        latest_year = int(
            _row(conn, "SELECT CAST(strftime('%Y', MAX(created_at)) AS INTEGER) AS y FROM orders")[
                "y"
            ]
        )
        last_calendar_year = latest_year - 1

        tasks: dict[str, Any] = {
            "hello": {
                "type": "deterministic-static",
                "prompt": TASKS["hello"],
                "expected": {"final_answer": "42"},
            },
            "reasoning": {
                "type": "deterministic-static",
                "prompt": TASKS["reasoning"],
                "expected": {"final_answer": "0.05"},
            },
            "hn-research": {
                "type": "external-dynamic",
                "prompt": TASKS["hn-research"],
                "expected": None,
                "notes": "No stable ground truth: depends on live Hacker News + web state.",
            },
        }

        tasks["adi-top-modules"] = {
            "type": "deterministic-sql",
            "prompt": TASKS["adi-top-modules"],
            "sql": """
                SELECT
                  p.name AS module_name,
                  c.name AS business_function,
                  COUNT(DISTINCT oi.order_id) AS activation_count,
                  ROUND(SUM(oi.seats * oi.unit_price), 2) AS subscription_revenue
                FROM order_items oi
                JOIN orders o ON o.id = oi.order_id
                JOIN products p ON p.id = oi.product_id
                JOIN categories c ON c.id = p.category_id
                WHERE o.status != 'cancelled'
                  AND o.created_at >= datetime(?, '-90 day')
                GROUP BY p.name, c.name
                ORDER BY activation_count DESC, subscription_revenue DESC
                LIMIT 5
            """,
            "expected": _rows(
                conn,
                """
                SELECT
                  p.name AS module_name,
                  c.name AS business_function,
                  COUNT(DISTINCT oi.order_id) AS activation_count,
                  ROUND(SUM(oi.seats * oi.unit_price), 2) AS subscription_revenue
                FROM order_items oi
                JOIN orders o ON o.id = oi.order_id
                JOIN products p ON p.id = oi.product_id
                JOIN categories c ON c.id = p.category_id
                WHERE o.status != 'cancelled'
                  AND o.created_at >= datetime(?, '-90 day')
                GROUP BY p.name, c.name
                ORDER BY activation_count DESC, subscription_revenue DESC
                LIMIT 5
                """,
                (max_created_at,),
            ),
        }

        tasks["adi-low-adoption"] = {
            "type": "deterministic-sql",
            "prompt": TASKS["adi-low-adoption"],
            "sql": """
                SELECT
                  p.name AS module_name,
                  c.name AS business_function,
                  MIN(p.active_deployments) AS active_deployments
                FROM products p
                JOIN categories c ON c.id = p.category_id
                WHERE p.active_deployments <= 25
                GROUP BY p.name, c.name
                ORDER BY active_deployments ASC, p.name ASC
            """,
            "expected": _rows(
                conn,
                """
                SELECT
                  p.name AS module_name,
                  c.name AS business_function,
                  MIN(p.active_deployments) AS active_deployments
                FROM products p
                JOIN categories c ON c.id = p.category_id
                WHERE p.active_deployments <= 25
                GROUP BY p.name, c.name
                ORDER BY active_deployments ASC, p.name ASC
                """,
            ),
        }

        tasks["adi-user-lookup"] = {
            "type": "deterministic-sql",
            "prompt": TASKS["adi-user-lookup"],
            "parameters": {"customer_id": 42},
            "expected": {
                "profile_and_lifetime": _row(
                    conn,
                    """
                    SELECT
                      c.id,
                      c.full_name,
                      c.email,
                      c.city,
                      c.country,
                      c.tier,
                      c.created_at,
                      ROUND(COALESCE(SUM(CASE WHEN o.status != 'cancelled' THEN o.total_amount END), 0), 2)
                        AS total_lifetime_spend
                    FROM customers c
                    LEFT JOIN orders o ON o.customer_id = c.id
                    WHERE c.id = ?
                    GROUP BY c.id, c.full_name, c.email, c.city, c.country, c.tier, c.created_at
                    """,
                    (42,),
                ),
                "last_5_subscriptions": _rows(
                    conn,
                    """
                    SELECT
                      o.id AS order_id,
                      o.status,
                      ROUND(o.total_amount, 2) AS total_amount,
                      o.created_at
                    FROM orders o
                    WHERE o.customer_id = ?
                    ORDER BY o.created_at DESC
                    LIMIT 5
                    """,
                    (42,),
                ),
            },
        }

        tasks["adi-function-analysis"] = {
            "type": "deterministic-sql",
            "prompt": TASKS["adi-function-analysis"],
            "expected": _rows(
                conn,
                """
                WITH function_revenue AS (
                  SELECT
                    c.id AS category_id,
                    c.name AS business_function,
                    ROUND(SUM(oi.seats * oi.unit_price), 2) AS revenue_6m,
                    COUNT(DISTINCT o.customer_id) AS unique_users_6m
                  FROM categories c
                  JOIN products p ON p.category_id = c.id
                  JOIN order_items oi ON oi.product_id = p.id
                  JOIN orders o ON o.id = oi.order_id
                  WHERE o.status != 'cancelled'
                    AND o.created_at >= datetime(?, '-6 months')
                  GROUP BY c.id, c.name
                ),
                module_revenue AS (
                  SELECT
                    c.id AS category_id,
                    p.name AS module_name,
                    ROUND(SUM(oi.seats * oi.unit_price), 2) AS module_revenue_6m,
                    ROW_NUMBER() OVER (
                      PARTITION BY c.id
                      ORDER BY SUM(oi.seats * oi.unit_price) DESC, p.name ASC
                    ) AS rn
                  FROM categories c
                  JOIN products p ON p.category_id = c.id
                  JOIN order_items oi ON oi.product_id = p.id
                  JOIN orders o ON o.id = oi.order_id
                  WHERE o.status != 'cancelled'
                    AND o.created_at >= datetime(?, '-6 months')
                  GROUP BY c.id, p.name
                )
                SELECT
                  fr.business_function,
                  fr.revenue_6m,
                  fr.unique_users_6m,
                  mr.module_name AS highest_revenue_module,
                  mr.module_revenue_6m AS highest_module_revenue_6m
                FROM function_revenue fr
                LEFT JOIN module_revenue mr ON mr.category_id = fr.category_id AND mr.rn = 1
                ORDER BY fr.revenue_6m DESC, fr.business_function ASC
                """,
                (max_created_at, max_created_at),
            ),
        }

        exec_users = _rows(
            conn,
            """
            WITH ltv AS (
              SELECT
                c.id AS customer_id,
                ROUND(COALESCE(SUM(CASE WHEN o.status != 'cancelled' THEN o.total_amount END), 0), 2)
                  AS lifetime_value
              FROM customers c
              LEFT JOIN orders o ON o.customer_id = c.id
              WHERE c.tier = 'gold'
              GROUP BY c.id
            ),
            best_order AS (
              SELECT
                o.customer_id,
                o.id AS best_subscription_id,
                ROUND(o.total_amount, 2) AS best_subscription_amount,
                ROW_NUMBER() OVER (
                  PARTITION BY o.customer_id
                  ORDER BY o.total_amount DESC, o.id ASC
                ) AS rn
              FROM orders o
              JOIN customers c ON c.id = o.customer_id
              WHERE c.tier = 'gold'
                AND o.status != 'cancelled'
            )
            SELECT
              c.id AS customer_id,
              c.full_name,
              c.city,
              l.lifetime_value,
              bo.best_subscription_id,
              bo.best_subscription_amount
            FROM customers c
            JOIN ltv l ON l.customer_id = c.id
            LEFT JOIN best_order bo ON bo.customer_id = c.id AND bo.rn = 1
            WHERE c.tier = 'gold'
            ORDER BY c.full_name ASC
            """
        )
        city_counts = _rows(
            conn,
            """
            SELECT city, COUNT(*) AS gold_user_count
            FROM customers
            WHERE tier = 'gold'
            GROUP BY city
            ORDER BY gold_user_count DESC, city ASC
            """
        )
        tasks["adi-executive-users"] = {
            "type": "deterministic-sql",
            "prompt": TASKS["adi-executive-users"],
            "expected": {
                "gold_users": exec_users,
                "city_counts": city_counts,
                "top_city": city_counts[0] if city_counts else None,
            },
        }

        highest = _rows(
            conn,
            """
            WITH ranked AS (
              SELECT
                p.name AS module_name,
                ROUND(AVG(r.rating), 3) AS avg_rating,
                COUNT(*) AS review_count,
                (
                  SELECT r2.title
                  FROM reviews r2
                  JOIN products p2 ON p2.id = r2.product_id
                  WHERE p2.name = p.name
                  ORDER BY r2.created_at DESC, r2.id DESC
                  LIMIT 1
                ) AS sample_review_title
              FROM products p
              JOIN reviews r ON r.product_id = p.id
              GROUP BY p.name
            )
            SELECT module_name, avg_rating, review_count, sample_review_title
            FROM ranked
            WHERE review_count >= 5
            ORDER BY avg_rating DESC, review_count DESC, module_name ASC
            LIMIT 3
            """
        )
        lowest = _rows(
            conn,
            """
            WITH ranked AS (
              SELECT
                p.name AS module_name,
                ROUND(AVG(r.rating), 3) AS avg_rating,
                COUNT(*) AS review_count,
                (
                  SELECT r2.title
                  FROM reviews r2
                  JOIN products p2 ON p2.id = r2.product_id
                  WHERE p2.name = p.name
                  ORDER BY r2.created_at DESC, r2.id DESC
                  LIMIT 1
                ) AS sample_review_title
              FROM products p
              JOIN reviews r ON r.product_id = p.id
              GROUP BY p.name
            )
            SELECT module_name, avg_rating, review_count, sample_review_title
            FROM ranked
            WHERE review_count >= 3
            ORDER BY avg_rating ASC, review_count DESC, module_name ASC
            LIMIT 3
            """
        )
        tasks["adi-module-ratings"] = {
            "type": "deterministic-sql",
            "prompt": TASKS["adi-module-ratings"],
            "expected": {"highest_3": highest, "lowest_3": lowest},
        }

        monthly = _rows(
            conn,
            """
            WITH monthly AS (
              SELECT
                strftime('%Y-%m', created_at) AS month,
                COUNT(*) AS activation_count,
                ROUND(SUM(total_amount), 2) AS revenue
              FROM orders
              WHERE status != 'cancelled'
                AND strftime('%Y', created_at) = ?
              GROUP BY strftime('%Y-%m', created_at)
            )
            SELECT month, activation_count, revenue
            FROM monthly
            ORDER BY month ASC
            """,
            (str(last_calendar_year),),
        )
        high_month = max(monthly, key=lambda x: x["revenue"]) if monthly else None
        low_month = min(monthly, key=lambda x: x["revenue"]) if monthly else None
        growth_pct = None
        if high_month and low_month and low_month["revenue"]:
            growth_pct = round(
                ((high_month["revenue"] - low_month["revenue"]) / low_month["revenue"]) * 100, 2
            )
        tasks["adi-monthly-trend"] = {
            "type": "deterministic-sql",
            "prompt": TASKS["adi-monthly-trend"],
            "expected": {
                "year": last_calendar_year,
                "monthly": monthly,
                "highest_revenue_month": high_month,
                "lowest_revenue_month": low_month,
                "growth_from_lowest_to_highest_pct": growth_pct,
            },
        }

        disengagement = _rows(
            conn,
            """
            WITH latest AS (
              SELECT MAX(created_at) AS max_created_at FROM orders
            ),
            user_stats AS (
              SELECT
                c.id AS customer_id,
                c.full_name,
                c.tier,
                COUNT(CASE WHEN o.status != 'cancelled' THEN 1 END) AS active_subscriptions,
                MAX(CASE WHEN o.status != 'cancelled' THEN o.created_at END) AS last_subscription_date,
                ROUND(COALESCE(SUM(CASE WHEN o.status != 'cancelled' THEN o.total_amount END), 0), 2)
                  AS lifetime_value
              FROM customers c
              LEFT JOIN orders o ON o.customer_id = c.id
              GROUP BY c.id, c.full_name, c.tier
            )
            SELECT
              us.customer_id,
              us.full_name,
              us.tier,
              us.last_subscription_date,
              us.lifetime_value
            FROM user_stats us
            CROSS JOIN latest l
            WHERE us.active_subscriptions >= 2
              AND us.last_subscription_date < datetime(l.max_created_at, '-180 day')
            ORDER BY us.lifetime_value DESC, us.customer_id ASC
            LIMIT 10
            """
        )
        tasks["adi-disengagement-risk"] = {
            "type": "deterministic-sql",
            "prompt": TASKS["adi-disengagement-risk"],
            "expected": disengagement,
        }

        portfolio = _rows(
            conn,
            """
            WITH non_cancelled_orders AS (
              SELECT o.id, o.customer_id, o.total_amount
              FROM orders o
              WHERE o.status != 'cancelled'
            ),
            order_item_counts AS (
              SELECT oi.order_id, COUNT(*) AS modules_per_subscription
              FROM order_items oi
              GROUP BY oi.order_id
            )
            SELECT
              c.tier,
              ROUND(AVG(oic.modules_per_subscription), 3) AS avg_modules_per_subscription,
              ROUND(AVG(nco.total_amount), 2) AS avg_subscription_value
            FROM non_cancelled_orders nco
            JOIN customers c ON c.id = nco.customer_id
            JOIN order_item_counts oic ON oic.order_id = nco.id
            GROUP BY c.tier
            ORDER BY c.tier ASC
            """
        )
        deepest = max(portfolio, key=lambda x: x["avg_modules_per_subscription"]) if portfolio else None
        tasks["adi-portfolio-depth"] = {
            "type": "deterministic-sql",
            "prompt": TASKS["adi-portfolio-depth"],
            "expected": {
                "by_tier": portfolio,
                "deepest_tier": deepest["tier"] if deepest else None,
                "deepest_avg_modules_per_subscription": (
                    deepest["avg_modules_per_subscription"] if deepest else None
                ),
            },
        }

        return {
            "generated_at": datetime.now(UTC).isoformat(),
            "db_path": str(DB_PATH),
            "max_order_created_at": max_created_at,
            "notes": [
                "Ground truth is deterministic for seeded SQLite data.",
                "Metric scoring can compare model outputs against expected fields/rows per task.",
                "hn-research is external-dynamic and excluded from strict deterministic scoring.",
            ],
            "tasks": tasks,
        }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate deterministic ground-truth answers for benchmark tasks."
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("reports/ground-truth.json"),
        help="Output JSON path (default: reports/ground-truth.json)",
    )
    args = parser.parse_args()

    payload = build_ground_truth()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"Saved ground truth to {args.output}")


if __name__ == "__main__":
    main()
