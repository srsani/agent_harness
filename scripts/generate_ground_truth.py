from __future__ import annotations

import argparse
import json
import math
import statistics
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


def _trailing_months(anchor_iso: str, n: int) -> list[str]:
    """Return n chronological 'YYYY-MM' strings ending at the anchor timestamp's month."""
    anchor = datetime.fromisoformat(anchor_iso)
    months: list[str] = []
    year, month = anchor.year, anchor.month
    for _ in range(n):
        months.append(f"{year:04d}-{month:02d}")
        month -= 1
        if month == 0:
            month = 12
            year -= 1
    return list(reversed(months))


def _trailing_complete_months(anchor_iso: str, n: int) -> list[str]:
    """Return n chronological 'YYYY-MM' strings ending at the last COMPLETE month before the
    anchor's month (the anchor's own calendar month is usually still in progress mid-benchmark-run
    and would otherwise look like an artificial revenue/activity dip)."""
    anchor = datetime.fromisoformat(anchor_iso)
    year, month = anchor.year, anchor.month
    month -= 1
    if month == 0:
        month = 12
        year -= 1
    last_complete = f"{year:04d}-{month:02d}-01T00:00:00"
    return _trailing_months(last_complete, n)


def _ids_sql(ids: list[int]) -> str:
    return ",".join(str(i) for i in ids)


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

        tasks["adi-function-opportunity"] = {
            "type": "deterministic-sql",
            "prompt": TASKS["adi-function-opportunity"],
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
                ),
                function_ratings AS (
                  SELECT
                    c.id AS category_id,
                    ROUND(AVG(r.rating), 3) AS avg_module_rating
                  FROM categories c
                  JOIN products p ON p.category_id = c.id
                  JOIN reviews r ON r.product_id = p.id
                  GROUP BY c.id
                ),
                low_adoption AS (
                  SELECT
                    c.id AS category_id,
                    COUNT(*) AS low_adoption_modules
                  FROM categories c
                  JOIN products p ON p.category_id = c.id
                  WHERE p.active_deployments <= 25
                  GROUP BY c.id
                )
                SELECT
                  fr.business_function,
                  fr.revenue_6m,
                  fr.unique_users_6m,
                  mr.module_name AS highest_revenue_module,
                  COALESCE(r.avg_module_rating, 0) AS avg_module_rating,
                  COALESCE(la.low_adoption_modules, 0) AS low_adoption_modules
                FROM function_revenue fr
                LEFT JOIN module_revenue mr ON mr.category_id = fr.category_id AND mr.rn = 1
                LEFT JOIN function_ratings r ON r.category_id = fr.category_id
                LEFT JOIN low_adoption la ON la.category_id = fr.category_id
                ORDER BY fr.revenue_6m DESC, fr.business_function ASC
                LIMIT 3
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
            """,
        )
        city_counts = _rows(
            conn,
            """
            SELECT city, COUNT(*) AS gold_user_count
            FROM customers
            WHERE tier = 'gold'
            GROUP BY city
            ORDER BY gold_user_count DESC, city ASC
            """,
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
            """,
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
            """,
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
            """,
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
            """,
        )
        deepest = (
            max(portfolio, key=lambda x: x["avg_modules_per_subscription"]) if portfolio else None
        )
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

        # ═══════════════════════════════════════════════════════════════════
        # Architecture routing benchmark — ground truth
        # See agent_harness/tasks/builtins.py for the matching prompts and
        # agent_harness/tasks/routing_benchmark.py for the "why this
        # architecture wins" explanations.
        # ═══════════════════════════════════════════════════════════════════

        # ── enterprise-react ──────────────────────────────────────────────
        tasks["react-customer-profile-77"] = {
            "type": "deterministic-sql",
            "prompt": TASKS["react-customer-profile-77"],
            "expected": _row(
                conn,
                """
                SELECT c.id, c.full_name, c.city, c.tier,
                       ROUND(COALESCE(SUM(CASE WHEN o.status != 'cancelled' THEN o.total_amount END), 0), 2)
                         AS lifetime_subscription_value
                FROM customers c
                LEFT JOIN orders o ON o.customer_id = c.id
                WHERE c.id = 77
                GROUP BY c.id
                """,
            ),
        }

        tasks["react-product-detail-15"] = {
            "type": "deterministic-sql",
            "prompt": TASKS["react-product-detail-15"],
            "expected": _row(
                conn,
                """
                SELECT p.id, p.name, c.name AS business_function, p.annual_license_usd,
                       p.active_deployments, ROUND(AVG(r.rating), 2) AS avg_rating,
                       COUNT(r.id) AS review_count
                FROM products p
                JOIN categories c ON c.id = p.category_id
                LEFT JOIN reviews r ON r.product_id = p.id
                WHERE p.id = 15
                GROUP BY p.id
                """,
            ),
        }

        tasks["react-low-adoption-threshold-20"] = {
            "type": "deterministic-sql",
            "prompt": TASKS["react-low-adoption-threshold-20"],
            "expected": _rows(
                conn,
                """
                SELECT p.name AS module_name, p.active_deployments
                FROM products p
                WHERE p.active_deployments <= 20
                ORDER BY p.active_deployments ASC, p.name ASC
                """,
            ),
        }

        tasks["react-top-modules-30days"] = {
            "type": "deterministic-sql",
            "prompt": TASKS["react-top-modules-30days"],
            "expected": _rows(
                conn,
                """
                SELECT p.name AS module_name,
                       COUNT(DISTINCT oi.order_id) AS activation_count
                FROM order_items oi
                JOIN orders o ON o.id = oi.order_id
                JOIN products p ON p.id = oi.product_id
                WHERE o.status != 'cancelled'
                  AND o.created_at >= datetime(?, '-30 day')
                GROUP BY p.id
                ORDER BY activation_count DESC, p.name ASC
                LIMIT 5
                """,
                (max_created_at,),
            ),
        }

        tasks["react-recent-reviews-module-8"] = {
            "type": "deterministic-sql",
            "prompt": TASKS["react-recent-reviews-module-8"],
            "expected": _rows(
                conn,
                """
                SELECT r.rating, r.title, c.full_name AS reviewer, r.created_at
                FROM reviews r
                JOIN customers c ON c.id = r.customer_id
                WHERE r.product_id = 8
                ORDER BY r.created_at DESC, r.id DESC
                LIMIT 5
                """,
            ),
        }

        tasks["react-sales-summary-60d"] = {
            "type": "deterministic-sql",
            "prompt": TASKS["react-sales-summary-60d"],
            "expected": _row(
                conn,
                """
                SELECT COUNT(DISTINCT o.id) AS total_subscriptions,
                       COUNT(DISTINCT o.customer_id) AS unique_users,
                       ROUND(SUM(o.total_amount), 2) AS total_revenue
                FROM orders o
                WHERE o.status != 'cancelled'
                  AND o.created_at >= datetime(?, '-60 day')
                  AND o.created_at <= ?
                """,
                (max_created_at, max_created_at),
            ),
        }

        tasks["react-category-catalogue"] = {
            "type": "deterministic-sql",
            "prompt": TASKS["react-category-catalogue"],
            "expected": _rows(conn, "SELECT name, description FROM categories ORDER BY name"),
        }

        tasks["react-search-products-supplychain"] = {
            "type": "deterministic-sql",
            "prompt": TASKS["react-search-products-supplychain"],
            "expected": _rows(
                conn,
                """
                SELECT p.name AS module_name, p.annual_license_usd
                FROM products p
                JOIN categories c ON c.id = p.category_id
                WHERE c.name LIKE '%Supply Chain%' AND p.annual_license_usd <= 9000
                ORDER BY p.name
                """,
            ),
        }

        tasks["react-search-customers-gold-london"] = {
            "type": "deterministic-sql",
            "prompt": TASKS["react-search-customers-gold-london"],
            "expected": _rows(
                conn,
                """
                SELECT full_name, email FROM customers
                WHERE tier = 'gold' AND city = 'London'
                ORDER BY full_name
                """,
            ),
        }

        tasks["react-customer-orders-history-130"] = {
            "type": "deterministic-sql",
            "prompt": TASKS["react-customer-orders-history-130"],
            "expected": _rows(
                conn,
                """
                SELECT o.id AS order_id, o.status, o.total_amount, o.created_at
                FROM orders o
                WHERE o.customer_id = 130
                ORDER BY o.created_at DESC
                LIMIT 20
                """,
            ),
        }

        tasks["react-order-detail-500"] = {
            "type": "deterministic-sql",
            "prompt": TASKS["react-order-detail-500"],
            "expected": {
                "header": _row(
                    conn,
                    """
                    SELECT o.id, o.status, o.total_amount, o.created_at,
                           c.full_name AS customer_name
                    FROM orders o
                    JOIN customers c ON c.id = o.customer_id
                    WHERE o.id = 500
                    """,
                ),
                "items": _rows(
                    conn,
                    """
                    SELECT p.name AS module_name, oi.seats, oi.unit_price,
                           ROUND(oi.seats * oi.unit_price, 2) AS line_total
                    FROM order_items oi
                    JOIN products p ON p.id = oi.product_id
                    WHERE oi.order_id = 500
                    ORDER BY p.name
                    """,
                ),
            },
        }

        tasks["react-customer-lifetime-value-17"] = {
            "type": "deterministic-sql",
            "prompt": TASKS["react-customer-lifetime-value-17"],
            "expected": _row(
                conn,
                """
                SELECT c.id, c.full_name,
                       ROUND(SUM(oi.seats * oi.unit_price), 2) AS total_spend,
                       (
                           SELECT cat.name
                           FROM order_items oi2
                           JOIN orders o2 ON o2.id = oi2.order_id
                           JOIN products p2 ON p2.id = oi2.product_id
                           JOIN categories cat ON cat.id = p2.category_id
                           WHERE o2.customer_id = c.id AND o2.status = 'delivered'
                           GROUP BY cat.id
                           ORDER BY SUM(oi2.seats * oi2.unit_price) DESC
                           LIMIT 1
                       ) AS top_business_function
                FROM customers c
                JOIN orders o ON o.customer_id = c.id
                JOIN order_items oi ON oi.order_id = o.id
                WHERE c.id = 17 AND o.status = 'delivered'
                GROUP BY c.id
                """,
            ),
        }

        # ── enterprise-codemode ───────────────────────────────────────────
        tasks["codemode-gold-lifetime-scan"] = {
            "type": "deterministic-sql",
            "prompt": TASKS["codemode-gold-lifetime-scan"],
            "expected": _rows(
                conn,
                """
                SELECT c.full_name, c.city,
                       ROUND(COALESCE(SUM(CASE WHEN o.status != 'cancelled' THEN o.total_amount END), 0), 2)
                         AS lifetime_value,
                       MAX(CASE WHEN o.status != 'cancelled' THEN o.created_at END)
                         AS most_recent_subscription_date
                FROM customers c
                LEFT JOIN orders o ON o.customer_id = c.id
                WHERE c.tier = 'gold'
                GROUP BY c.id
                ORDER BY lifetime_value DESC, c.full_name ASC
                LIMIT 10
                """,
            ),
        }

        codemode_batch_ids = [
            3,
            17,
            24,
            38,
            45,
            52,
            61,
            74,
            88,
            93,
            101,
            115,
            122,
            136,
            149,
            158,
            163,
            171,
            184,
            197,
        ]
        tasks["codemode-customer-batch-lookup"] = {
            "type": "deterministic-sql",
            "prompt": TASKS["codemode-customer-batch-lookup"],
            "expected": _rows(
                conn,
                f"""
                SELECT c.full_name, c.tier,
                       ROUND(COALESCE(SUM(CASE WHEN o.status != 'cancelled' THEN o.total_amount END), 0), 2)
                         AS lifetime_value
                FROM customers c
                LEFT JOIN orders o ON o.customer_id = c.id
                WHERE c.id IN ({_ids_sql(codemode_batch_ids)}) AND c.tier = 'gold'
                GROUP BY c.id
                ORDER BY lifetime_value DESC, c.full_name ASC
                """,
            ),
        }

        review_gap_ids = [
            2,
            5,
            9,
            12,
            18,
            22,
            27,
            31,
            34,
            39,
            43,
            47,
            52,
            56,
            61,
            65,
            70,
            74,
            79,
            83,
            88,
            92,
            97,
            100,
        ]
        tasks["codemode-module-review-gap-scan"] = {
            "type": "deterministic-sql",
            "prompt": TASKS["codemode-module-review-gap-scan"],
            "expected": _rows(
                conn,
                f"""
                SELECT p.name AS module_name, c.name AS business_function, p.active_deployments
                FROM products p
                JOIN categories c ON c.id = p.category_id
                LEFT JOIN reviews r ON r.product_id = p.id
                WHERE p.id IN ({_ids_sql(review_gap_ids)})
                GROUP BY p.id
                HAVING COUNT(r.id) = 0
                ORDER BY p.name
                """,
            ),
        }

        order_audit_ids = [
            5,
            40,
            85,
            120,
            200,
            260,
            310,
            375,
            430,
            500,
            560,
            610,
            670,
            740,
            800,
            860,
            920,
            980,
            1040,
            1100,
        ]
        tasks["codemode-order-batch-audit"] = {
            "type": "deterministic-sql",
            "prompt": TASKS["codemode-order-batch-audit"],
            "expected": {
                "delivered_total_amount": _row(
                    conn,
                    f"""
                    SELECT ROUND(COALESCE(SUM(total_amount), 0), 2) AS total
                    FROM orders
                    WHERE id IN ({_ids_sql(order_audit_ids)}) AND status = 'delivered'
                    """,
                )["total"],
                "distinct_modules": [
                    r["module_name"]
                    for r in _rows(
                        conn,
                        f"""
                        SELECT DISTINCT p.name AS module_name
                        FROM order_items oi
                        JOIN products p ON p.id = oi.product_id
                        WHERE oi.order_id IN ({_ids_sql(order_audit_ids)})
                        ORDER BY module_name
                        """,
                    )
                ],
            },
        }

        tasks["codemode-top-module-review-quality"] = {
            "type": "deterministic-sql",
            "prompt": TASKS["codemode-top-module-review-quality"],
            "expected": _rows(
                conn,
                """
                WITH top10 AS (
                    SELECT p.id, p.name AS module_name,
                           COUNT(DISTINCT oi.order_id) AS activation_count
                    FROM order_items oi
                    JOIN orders o ON o.id = oi.order_id
                    JOIN products p ON p.id = oi.product_id
                    WHERE o.status != 'cancelled'
                      AND o.created_at >= datetime(?, '-90 day')
                    GROUP BY p.id
                    ORDER BY activation_count DESC, module_name ASC
                    LIMIT 10
                )
                SELECT t.module_name, t.activation_count,
                       ROUND(100.0 * SUM(CASE WHEN r.rating >= 4 THEN 1 ELSE 0 END)
                             / NULLIF(COUNT(r.id), 0), 2) AS pct_4_5_star
                FROM top10 t
                LEFT JOIN reviews r ON r.product_id = t.id
                GROUP BY t.id
                ORDER BY pct_4_5_star DESC, t.activation_count DESC
                """,
                (max_created_at,),
            ),
        }

        tasks["codemode-gold-churn-scan"] = {
            "type": "deterministic-sql",
            "prompt": TASKS["codemode-gold-churn-scan"],
            "expected": _rows(
                conn,
                """
                SELECT c.full_name, c.city, MAX(o.created_at) AS most_recent_subscription_date
                FROM customers c
                LEFT JOIN orders o ON o.customer_id = c.id
                WHERE c.tier = 'gold'
                GROUP BY c.id
                HAVING most_recent_subscription_date IS NULL
                    OR most_recent_subscription_date < datetime(?, '-120 day')
                ORDER BY c.full_name
                """,
                (max_created_at,),
            ),
        }

        tasks["codemode-lowstock-unreviewed"] = {
            "type": "deterministic-sql",
            "prompt": TASKS["codemode-lowstock-unreviewed"],
            "expected": _rows(
                conn,
                """
                SELECT p.name AS module_name, c.name AS business_function, p.active_deployments
                FROM products p
                JOIN categories c ON c.id = p.category_id
                LEFT JOIN reviews r ON r.product_id = p.id
                WHERE p.active_deployments <= 25
                GROUP BY p.id
                HAVING COUNT(r.id) = 0
                ORDER BY p.active_deployments ASC, p.name ASC
                """,
            ),
        }

        tasks["codemode-category-price-spread"] = {
            "type": "deterministic-sql",
            "prompt": TASKS["codemode-category-price-spread"],
            "expected": _rows(
                conn,
                """
                SELECT c.name AS business_function,
                       MIN(p.annual_license_usd) AS min_price,
                       MAX(p.annual_license_usd) AS max_price,
                       ROUND(AVG(p.annual_license_usd), 2) AS avg_price
                FROM products p
                JOIN categories c ON c.id = p.category_id
                GROUP BY c.id
                ORDER BY c.name
                """,
            ),
        }

        tasks["codemode-recent-multi-subscribers"] = {
            "type": "deterministic-sql",
            "prompt": TASKS["codemode-recent-multi-subscribers"],
            "expected": _rows(
                conn,
                """
                SELECT c.full_name,
                       COUNT(o.id) AS recent_subscription_count,
                       ROUND(SUM(o.total_amount), 2) AS recent_total_spend
                FROM customers c
                JOIN orders o ON o.customer_id = c.id
                WHERE c.id BETWEEN 150 AND 170
                  AND o.created_at >= datetime(?, '-90 day')
                GROUP BY c.id
                HAVING COUNT(o.id) >= 2
                ORDER BY recent_subscription_count DESC, c.full_name ASC
                """,
                (max_created_at,),
            ),
        }

        bundle_scan_ids = [
            10,
            55,
            100,
            150,
            210,
            260,
            320,
            370,
            430,
            480,
            540,
            590,
            650,
            700,
            760,
            810,
            870,
            920,
            980,
            1030,
        ]
        bundle_rows = _rows(
            conn,
            f"""
            SELECT o.id AS order_id, c.full_name AS customer_name, o.status, p.name AS module_name
            FROM orders o
            JOIN customers c ON c.id = o.customer_id
            JOIN order_items oi ON oi.order_id = o.id
            JOIN products p ON p.id = oi.product_id
            WHERE o.id IN ({_ids_sql(bundle_scan_ids)})
            ORDER BY o.id, p.name
            """,
        )
        bundle_grouped: dict[int, dict[str, Any]] = {}
        for r in bundle_rows:
            g = bundle_grouped.setdefault(
                r["order_id"],
                {
                    "order_id": r["order_id"],
                    "customer_name": r["customer_name"],
                    "status": r["status"],
                    "modules": [],
                },
            )
            g["modules"].append(r["module_name"])
        tasks["codemode-bundle-scan"] = {
            "type": "deterministic-sql",
            "prompt": TASKS["codemode-bundle-scan"],
            "expected": sorted(
                (g for g in bundle_grouped.values() if len(g["modules"]) >= 3),
                key=lambda g: g["order_id"],
            ),
        }

        tasks["codemode-most-reviewed-deepdive"] = {
            "type": "deterministic-sql",
            "prompt": TASKS["codemode-most-reviewed-deepdive"],
            "expected": _rows(
                conn,
                """
                WITH counts AS (
                    SELECT p.id, p.name AS module_name, COUNT(r.id) AS review_count,
                           ROUND(AVG(r.rating), 2) AS avg_rating
                    FROM products p
                    JOIN reviews r ON r.product_id = p.id
                    GROUP BY p.id
                )
                SELECT module_name, review_count, avg_rating,
                       (
                           SELECT r2.title FROM reviews r2
                           WHERE r2.product_id = counts.id
                           ORDER BY r2.created_at DESC, r2.id DESC LIMIT 1
                       ) AS most_recent_review_title
                FROM counts
                ORDER BY review_count DESC, module_name ASC
                LIMIT 10
                """,
            ),
        }

        tasks["codemode-early-cohort-value"] = {
            "type": "deterministic-sql",
            "prompt": TASKS["codemode-early-cohort-value"],
            "expected": _rows(
                conn,
                """
                WITH earliest AS (SELECT MIN(created_at) AS min_created FROM customers)
                SELECT c.full_name, c.created_at,
                       ROUND(COALESCE(SUM(CASE WHEN o.status != 'cancelled' THEN o.total_amount END), 0), 2)
                         AS lifetime_value
                FROM customers c
                CROSS JOIN earliest e
                LEFT JOIN orders o ON o.customer_id = c.id
                WHERE c.created_at <= datetime(e.min_created, '+90 day')
                GROUP BY c.id
                ORDER BY lifetime_value DESC, c.full_name ASC
                LIMIT 10
                """,
            ),
        }

        # ── enterprise-mcp-react ──────────────────────────────────────────
        tasks["mcpreact-customer-profile-155"] = {
            "type": "deterministic-sql",
            "prompt": TASKS["mcpreact-customer-profile-155"],
            "expected": _row(
                conn,
                """
                SELECT c.full_name, c.email, c.city, c.tier,
                       ROUND(COALESCE(SUM(CASE WHEN o.status != 'cancelled' THEN o.total_amount END), 0), 2)
                         AS lifetime_subscription_value
                FROM customers c
                LEFT JOIN orders o ON o.customer_id = c.id
                WHERE c.id = 155
                GROUP BY c.id
                """,
            ),
        }

        tasks["mcpreact-product-detail-40"] = {
            "type": "deterministic-sql",
            "prompt": TASKS["mcpreact-product-detail-40"],
            "expected": _row(
                conn,
                """
                SELECT p.name, p.annual_license_usd, p.active_deployments,
                       ROUND(AVG(r.rating), 2) AS avg_rating
                FROM products p
                LEFT JOIN reviews r ON r.product_id = p.id
                WHERE p.id = 40
                GROUP BY p.id
                """,
            ),
        }

        tasks["mcpreact-low-adoption-threshold-15"] = {
            "type": "deterministic-sql",
            "prompt": TASKS["mcpreact-low-adoption-threshold-15"],
            "expected": _rows(
                conn,
                """
                SELECT p.name AS module_name, p.active_deployments
                FROM products p
                WHERE p.active_deployments <= 15
                ORDER BY p.active_deployments ASC, p.name ASC
                """,
            ),
        }

        tasks["mcpreact-top-modules-45days"] = {
            "type": "deterministic-sql",
            "prompt": TASKS["mcpreact-top-modules-45days"],
            "expected": _rows(
                conn,
                """
                SELECT p.name AS module_name,
                       COUNT(DISTINCT oi.order_id) AS activation_count
                FROM order_items oi
                JOIN orders o ON o.id = oi.order_id
                JOIN products p ON p.id = oi.product_id
                WHERE o.status != 'cancelled'
                  AND o.created_at >= datetime(?, '-45 day')
                GROUP BY p.id
                ORDER BY activation_count DESC, p.name ASC
                LIMIT 5
                """,
                (max_created_at,),
            ),
        }

        tasks["mcpreact-recent-reviews-module-60"] = {
            "type": "deterministic-sql",
            "prompt": TASKS["mcpreact-recent-reviews-module-60"],
            "expected": _rows(
                conn,
                """
                SELECT r.rating, r.title
                FROM reviews r
                WHERE r.product_id = 60
                ORDER BY r.created_at DESC, r.id DESC
                LIMIT 3
                """,
            ),
        }

        tasks["mcpreact-sales-summary-30d"] = {
            "type": "deterministic-sql",
            "prompt": TASKS["mcpreact-sales-summary-30d"],
            "expected": _row(
                conn,
                """
                SELECT COUNT(DISTINCT o.id) AS total_subscriptions,
                       COUNT(DISTINCT o.customer_id) AS unique_users,
                       ROUND(SUM(o.total_amount), 2) AS total_revenue
                FROM orders o
                WHERE o.status != 'cancelled'
                  AND o.created_at >= datetime(?, '-30 day')
                  AND o.created_at <= ?
                """,
                (max_created_at, max_created_at),
            ),
        }

        tasks["mcpreact-search-products-finance"] = {
            "type": "deterministic-sql",
            "prompt": TASKS["mcpreact-search-products-finance"],
            "expected": _rows(
                conn,
                """
                SELECT p.name AS module_name, p.annual_license_usd
                FROM products p
                JOIN categories c ON c.id = p.category_id
                WHERE c.name = 'Finance' AND p.annual_license_usd <= 8000
                ORDER BY p.name
                """,
            ),
        }

        tasks["mcpreact-search-customers-silver-berlin"] = {
            "type": "deterministic-sql",
            "prompt": TASKS["mcpreact-search-customers-silver-berlin"],
            "expected": _rows(
                conn,
                """
                SELECT full_name, email FROM customers
                WHERE tier = 'silver' AND city = 'Berlin'
                ORDER BY full_name
                """,
            ),
        }

        tasks["mcpreact-customer-orders-history-180"] = {
            "type": "deterministic-sql",
            "prompt": TASKS["mcpreact-customer-orders-history-180"],
            "expected": _rows(
                conn,
                """
                SELECT o.id AS order_id, o.status, o.total_amount, o.created_at
                FROM orders o
                WHERE o.customer_id = 180
                ORDER BY o.created_at DESC
                LIMIT 20
                """,
            ),
        }

        tasks["mcpreact-order-detail-900"] = {
            "type": "deterministic-sql",
            "prompt": TASKS["mcpreact-order-detail-900"],
            "expected": {
                "header": _row(
                    conn,
                    """
                    SELECT o.id, o.status, o.total_amount, o.created_at,
                           c.full_name AS customer_name
                    FROM orders o
                    JOIN customers c ON c.id = o.customer_id
                    WHERE o.id = 900
                    """,
                ),
                "items": _rows(
                    conn,
                    """
                    SELECT p.name AS module_name, oi.seats, oi.unit_price,
                           ROUND(oi.seats * oi.unit_price, 2) AS line_total
                    FROM order_items oi
                    JOIN products p ON p.id = oi.product_id
                    WHERE oi.order_id = 900
                    ORDER BY p.name
                    """,
                ),
            },
        }

        tasks["mcpreact-customer-lifetime-value-110"] = {
            "type": "deterministic-sql",
            "prompt": TASKS["mcpreact-customer-lifetime-value-110"],
            "expected": _row(
                conn,
                """
                SELECT c.id, c.full_name,
                       ROUND(SUM(oi.seats * oi.unit_price), 2) AS total_spend,
                       (
                           SELECT cat.name
                           FROM order_items oi2
                           JOIN orders o2 ON o2.id = oi2.order_id
                           JOIN products p2 ON p2.id = oi2.product_id
                           JOIN categories cat ON cat.id = p2.category_id
                           WHERE o2.customer_id = c.id AND o2.status = 'delivered'
                           GROUP BY cat.id
                           ORDER BY SUM(oi2.seats * oi2.unit_price) DESC
                           LIMIT 1
                       ) AS top_business_function
                FROM customers c
                JOIN orders o ON o.customer_id = c.id
                JOIN order_items oi ON oi.order_id = o.id
                WHERE c.id = 110 AND o.status = 'delivered'
                GROUP BY c.id
                """,
            ),
        }

        tasks["mcpreact-revenue-by-month-lastyear"] = {
            "type": "deterministic-sql",
            "prompt": TASKS["mcpreact-revenue-by-month-lastyear"],
            "expected": _rows(
                conn,
                """
                SELECT strftime('%Y-%m', created_at) AS month,
                       COUNT(*) AS subscriptions,
                       ROUND(SUM(total_amount), 2) AS revenue
                FROM orders
                WHERE status != 'cancelled'
                  AND strftime('%Y', created_at) = ?
                GROUP BY month
                ORDER BY month
                """,
                (str(last_calendar_year),),
            ),
        }

        # ── enterprise-mcp-codemode ───────────────────────────────────────
        tasks["mcpcodemode-silver-lifetime-scan"] = {
            "type": "deterministic-sql",
            "prompt": TASKS["mcpcodemode-silver-lifetime-scan"],
            "expected": _rows(
                conn,
                """
                SELECT c.full_name, c.city,
                       ROUND(COALESCE(SUM(CASE WHEN o.status != 'cancelled' THEN o.total_amount END), 0), 2)
                         AS lifetime_value,
                       COUNT(CASE WHEN o.status != 'cancelled' THEN o.id END) AS subscription_count
                FROM customers c
                LEFT JOIN orders o ON o.customer_id = c.id
                WHERE c.tier = 'silver'
                GROUP BY c.id
                ORDER BY lifetime_value DESC, c.full_name ASC
                LIMIT 10
                """,
            ),
        }

        mcp_batch_ids = [
            6,
            19,
            28,
            33,
            47,
            55,
            66,
            71,
            84,
            96,
            108,
            119,
            127,
            141,
            152,
            160,
            169,
            176,
            188,
            199,
        ]
        tasks["mcpcodemode-customer-batch-lookup"] = {
            "type": "deterministic-sql",
            "prompt": TASKS["mcpcodemode-customer-batch-lookup"],
            "expected": _rows(
                conn,
                f"""
                SELECT c.full_name, c.tier,
                       ROUND(COALESCE(SUM(CASE WHEN o.status != 'cancelled' THEN o.total_amount END), 0), 2)
                         AS lifetime_value
                FROM customers c
                LEFT JOIN orders o ON o.customer_id = c.id
                WHERE c.id IN ({_ids_sql(mcp_batch_ids)}) AND c.tier = 'silver'
                GROUP BY c.id
                ORDER BY lifetime_value DESC, c.full_name ASC
                """,
            ),
        }

        tasks["mcpcodemode-module-review-gap-scan-rd"] = {
            "type": "deterministic-sql",
            "prompt": TASKS["mcpcodemode-module-review-gap-scan-rd"],
            "expected": _rows(
                conn,
                """
                SELECT p.name AS module_name, p.active_deployments
                FROM products p
                JOIN categories c ON c.id = p.category_id
                LEFT JOIN reviews r ON r.product_id = p.id
                WHERE c.name = 'Research & Development'
                GROUP BY p.id
                HAVING COUNT(r.id) = 0
                ORDER BY p.name
                """,
            ),
        }

        mcp_order_audit_ids = [
            15,
            60,
            95,
            140,
            190,
            250,
            300,
            355,
            410,
            470,
            520,
            580,
            630,
            690,
            750,
            820,
            880,
            940,
            1000,
            1060,
            1120,
            1180,
        ]
        tasks["mcpcodemode-order-batch-audit"] = {
            "type": "deterministic-sql",
            "prompt": TASKS["mcpcodemode-order-batch-audit"],
            "expected": {
                "shipped_total_amount": _row(
                    conn,
                    f"""
                    SELECT ROUND(COALESCE(SUM(total_amount), 0), 2) AS total
                    FROM orders
                    WHERE id IN ({_ids_sql(mcp_order_audit_ids)}) AND status = 'shipped'
                    """,
                )["total"],
                "distinct_business_functions": [
                    r["business_function"]
                    for r in _rows(
                        conn,
                        f"""
                        SELECT DISTINCT c.name AS business_function
                        FROM order_items oi
                        JOIN products p ON p.id = oi.product_id
                        JOIN categories c ON c.id = p.category_id
                        WHERE oi.order_id IN ({_ids_sql(mcp_order_audit_ids)})
                        ORDER BY business_function
                        """,
                    )
                ],
            },
        }

        tasks["mcpcodemode-top-module-price-value"] = {
            "type": "deterministic-sql",
            "prompt": TASKS["mcpcodemode-top-module-price-value"],
            "expected": _rows(
                conn,
                """
                WITH top10 AS (
                    SELECT p.id, p.name AS module_name, p.active_deployments,
                           COUNT(DISTINCT oi.order_id) AS activation_count,
                           ROUND(SUM(oi.seats * oi.unit_price), 2) AS subscription_revenue
                    FROM order_items oi
                    JOIN orders o ON o.id = oi.order_id
                    JOIN products p ON p.id = oi.product_id
                    WHERE o.status != 'cancelled'
                      AND o.created_at >= datetime(?, '-60 day')
                    GROUP BY p.id
                    ORDER BY activation_count DESC, subscription_revenue DESC
                    LIMIT 10
                )
                SELECT module_name, activation_count, active_deployments,
                       ROUND(subscription_revenue / NULLIF(active_deployments, 0), 4)
                         AS revenue_per_deployment
                FROM top10
                ORDER BY revenue_per_deployment DESC
                """,
                (max_created_at,),
            ),
        }

        tasks["mcpcodemode-silver-churn-scan"] = {
            "type": "deterministic-sql",
            "prompt": TASKS["mcpcodemode-silver-churn-scan"],
            "expected": _rows(
                conn,
                """
                SELECT c.full_name, c.city, MAX(o.created_at) AS most_recent_subscription_date
                FROM customers c
                LEFT JOIN orders o ON o.customer_id = c.id
                WHERE c.tier = 'silver'
                GROUP BY c.id
                HAVING most_recent_subscription_date IS NULL
                    OR most_recent_subscription_date < datetime(?, '-150 day')
                ORDER BY c.full_name
                """,
                (max_created_at,),
            ),
        }

        tasks["mcpcodemode-highprice-lowrating-scan"] = {
            "type": "deterministic-sql",
            "prompt": TASKS["mcpcodemode-highprice-lowrating-scan"],
            "expected": _rows(
                conn,
                """
                SELECT p.name AS module_name, ROUND(AVG(r.rating), 2) AS avg_rating
                FROM products p
                LEFT JOIN reviews r ON r.product_id = p.id
                WHERE p.annual_license_usd >= 12000
                GROUP BY p.id
                HAVING AVG(r.rating) IS NULL OR AVG(r.rating) < 3.5
                ORDER BY avg_rating ASC, p.name ASC
                """,
            ),
        }

        tasks["mcpcodemode-category-deployment-spread"] = {
            "type": "deterministic-sql",
            "prompt": TASKS["mcpcodemode-category-deployment-spread"],
            "expected": _rows(
                conn,
                """
                SELECT c.name AS business_function,
                       MIN(p.active_deployments) AS min_deployments,
                       MAX(p.active_deployments) AS max_deployments,
                       ROUND(AVG(p.active_deployments), 2) AS avg_deployments
                FROM products p
                JOIN categories c ON c.id = p.category_id
                GROUP BY c.id
                ORDER BY c.name
                """,
            ),
        }

        tasks["mcpcodemode-recent-multi-subscribers"] = {
            "type": "deterministic-sql",
            "prompt": TASKS["mcpcodemode-recent-multi-subscribers"],
            "expected": _rows(
                conn,
                """
                SELECT c.full_name,
                       COUNT(o.id) AS recent_subscription_count,
                       ROUND(SUM(o.total_amount), 2) AS recent_total_spend
                FROM customers c
                JOIN orders o ON o.customer_id = c.id
                WHERE c.id BETWEEN 1 AND 40
                  AND o.created_at >= datetime(?, '-60 day')
                GROUP BY c.id
                HAVING COUNT(o.id) >= 2
                ORDER BY recent_subscription_count DESC, c.full_name ASC
                """,
                (max_created_at,),
            ),
        }

        mcp_bundle_ids = [
            20,
            65,
            110,
            160,
            220,
            270,
            330,
            380,
            440,
            490,
            550,
            600,
            660,
            710,
            770,
            820,
            890,
            930,
            990,
            1040,
        ]
        mcp_bundle_rows = _rows(
            conn,
            f"""
            SELECT o.id AS order_id, c.full_name AS customer_name, o.status, p.name AS module_name
            FROM orders o
            JOIN customers c ON c.id = o.customer_id
            JOIN order_items oi ON oi.order_id = o.id
            JOIN products p ON p.id = oi.product_id
            WHERE o.id IN ({_ids_sql(mcp_bundle_ids)})
            ORDER BY o.id, p.name
            """,
        )
        mcp_bundle_grouped: dict[int, dict[str, Any]] = {}
        for r in mcp_bundle_rows:
            g = mcp_bundle_grouped.setdefault(
                r["order_id"],
                {
                    "order_id": r["order_id"],
                    "customer_name": r["customer_name"],
                    "status": r["status"],
                    "modules": [],
                },
            )
            g["modules"].append(r["module_name"])
        tasks["mcpcodemode-bundle-scan"] = {
            "type": "deterministic-sql",
            "prompt": TASKS["mcpcodemode-bundle-scan"],
            "expected": sorted(
                (g for g in mcp_bundle_grouped.values() if len(g["modules"]) >= 4),
                key=lambda g: g["order_id"],
            ),
        }

        tasks["mcpcodemode-least-reviewed-deepdive"] = {
            "type": "deterministic-sql",
            "prompt": TASKS["mcpcodemode-least-reviewed-deepdive"],
            "expected": _rows(
                conn,
                """
                WITH counts AS (
                    SELECT p.id, p.name AS module_name, COUNT(r.id) AS review_count,
                           ROUND(AVG(r.rating), 2) AS avg_rating
                    FROM products p
                    JOIN reviews r ON r.product_id = p.id
                    GROUP BY p.id
                )
                SELECT module_name, review_count, avg_rating,
                       (
                           SELECT r2.title FROM reviews r2
                           WHERE r2.product_id = counts.id
                           ORDER BY r2.created_at ASC, r2.id ASC LIMIT 1
                       ) AS earliest_review_title
                FROM counts
                ORDER BY review_count ASC, module_name ASC
                LIMIT 10
                """,
            ),
        }

        tasks["mcpcodemode-recent-cohort-value"] = {
            "type": "deterministic-sql",
            "prompt": TASKS["mcpcodemode-recent-cohort-value"],
            "expected": _rows(
                conn,
                """
                WITH latest AS (SELECT MAX(created_at) AS max_created FROM customers)
                SELECT c.full_name, c.created_at,
                       ROUND(COALESCE(SUM(CASE WHEN o.status != 'cancelled' THEN o.total_amount END), 0), 2)
                         AS lifetime_value
                FROM customers c
                CROSS JOIN latest l
                LEFT JOIN orders o ON o.customer_id = c.id
                WHERE c.created_at >= datetime(l.max_created, '-90 day')
                GROUP BY c.id
                ORDER BY lifetime_value DESC, c.full_name ASC
                LIMIT 10
                """,
            ),
        }

        # ── enterprise-sql-react ──────────────────────────────────────────
        tasks["sqlreact-module-affinity"] = {
            "type": "deterministic-sql",
            "prompt": TASKS["sqlreact-module-affinity"],
            "expected": _row(
                conn,
                """
                SELECT p1.name AS module_a, p2.name AS module_b,
                       COUNT(DISTINCT a.order_id) AS co_occurrence_count
                FROM order_items a
                JOIN order_items b ON a.order_id = b.order_id AND a.product_id < b.product_id
                JOIN products p1 ON p1.id = a.product_id
                JOIN products p2 ON p2.id = b.product_id
                GROUP BY a.product_id, b.product_id
                ORDER BY co_occurrence_count DESC, module_a ASC, module_b ASC
                LIMIT 1
                """,
            ),
        }

        _all_prices = [
            r["annual_license_usd"] for r in _rows(conn, "SELECT annual_license_usd FROM products")
        ]
        tasks["sqlreact-median-price"] = {
            "type": "deterministic-computed",
            "prompt": TASKS["sqlreact-median-price"],
            "expected": {"median_annual_license_usd": round(statistics.median(_all_prices), 2)},
        }

        tasks["sqlreact-revenue-per-module-efficiency"] = {
            "type": "deterministic-sql",
            "prompt": TASKS["sqlreact-revenue-per-module-efficiency"],
            "expected": _rows(
                conn,
                """
                WITH rev AS (
                    SELECT c.id AS category_id, c.name AS business_function,
                           ROUND(SUM(oi.seats * oi.unit_price), 2) AS revenue,
                           (SELECT COUNT(*) FROM products p2 WHERE p2.category_id = c.id) AS module_count
                    FROM categories c
                    JOIN products p ON p.category_id = c.id
                    JOIN order_items oi ON oi.product_id = p.id
                    JOIN orders o ON o.id = oi.order_id
                    WHERE o.status != 'cancelled'
                    GROUP BY c.id
                )
                SELECT business_function, revenue, module_count,
                       ROUND(revenue * 1.0 / module_count, 2) AS revenue_per_module
                FROM rev
                ORDER BY revenue_per_module DESC
                """,
            ),
        }

        tasks["sqlreact-cross-functional-power-users"] = {
            "type": "deterministic-sql",
            "prompt": TASKS["sqlreact-cross-functional-power-users"],
            "expected": _rows(
                conn,
                """
                SELECT c.full_name, COUNT(DISTINCT cat.id) AS distinct_business_functions
                FROM customers c
                JOIN orders o ON o.customer_id = c.id AND o.status != 'cancelled'
                JOIN order_items oi ON oi.order_id = o.id
                JOIN products p ON p.id = oi.product_id
                JOIN categories cat ON cat.id = p.category_id
                GROUP BY c.id
                HAVING COUNT(DISTINCT cat.id) >= 4
                ORDER BY distinct_business_functions DESC, c.full_name ASC
                """,
            ),
        }

        _bundle_counts_row = _row(
            conn,
            """
            WITH counts AS (
                SELECT o.id, COUNT(oi.id) AS item_count
                FROM orders o
                JOIN order_items oi ON oi.order_id = o.id
                WHERE o.status != 'cancelled'
                GROUP BY o.id
            )
            SELECT COUNT(*) AS total, SUM(CASE WHEN item_count > 2 THEN 1 ELSE 0 END) AS bundles
            FROM counts
            """,
        )
        _bundle_pct = (
            round((_bundle_counts_row["bundles"] or 0) / _bundle_counts_row["total"] * 100, 2)
            if _bundle_counts_row and _bundle_counts_row["total"]
            else None
        )
        tasks["sqlreact-bundle-percentage"] = {
            "type": "deterministic-computed",
            "prompt": TASKS["sqlreact-bundle-percentage"],
            "expected": {
                "total_non_cancelled_subscriptions": _bundle_counts_row["total"],
                "bundles_over_2_modules": _bundle_counts_row["bundles"],
                "bundle_percentage": _bundle_pct,
            },
        }

        tasks["sqlreact-tier-rating-gap"] = {
            "type": "deterministic-sql",
            "prompt": TASKS["sqlreact-tier-rating-gap"],
            "expected": _rows(
                conn,
                """
                WITH gold AS (
                    SELECT r.product_id, AVG(r.rating) AS avg_rating
                    FROM reviews r
                    JOIN customers c ON c.id = r.customer_id
                    WHERE c.tier = 'gold'
                    GROUP BY r.product_id
                ),
                standard AS (
                    SELECT r.product_id, AVG(r.rating) AS avg_rating
                    FROM reviews r
                    JOIN customers c ON c.id = r.customer_id
                    WHERE c.tier = 'standard'
                    GROUP BY r.product_id
                )
                SELECT p.name AS module_name,
                       ROUND(g.avg_rating, 2) AS gold_avg_rating,
                       ROUND(s.avg_rating, 2) AS standard_avg_rating,
                       ROUND(ABS(g.avg_rating - s.avg_rating), 2) AS rating_gap
                FROM gold g
                JOIN standard s ON s.product_id = g.product_id
                JOIN products p ON p.id = g.product_id
                WHERE ABS(g.avg_rating - s.avg_rating) > 1.0
                ORDER BY rating_gap DESC, p.name ASC
                """,
            ),
        }

        tasks["sqlreact-fast-movers"] = {
            "type": "deterministic-sql",
            "prompt": TASKS["sqlreact-fast-movers"],
            "expected": _rows(
                conn,
                """
                WITH first_order AS (
                    SELECT o.customer_id, MIN(o.created_at) AS first_order_at
                    FROM orders o
                    WHERE o.status != 'cancelled'
                    GROUP BY o.customer_id
                )
                SELECT c.full_name,
                       CAST(JULIANDAY(f.first_order_at) - JULIANDAY(c.created_at) AS INTEGER)
                         AS days_to_first_subscription
                FROM customers c
                JOIN first_order f ON f.customer_id = c.id
                WHERE JULIANDAY(f.first_order_at) - JULIANDAY(c.created_at) BETWEEN 0 AND 7
                ORDER BY days_to_first_subscription ASC, c.full_name ASC
                """,
            ),
        }

        _mom_months = _trailing_complete_months(max_created_at, 7)
        _mom_counts: dict[str, int] = {}
        for _ms in _mom_months:
            _row_n = _row(
                conn,
                """
                SELECT COUNT(DISTINCT customer_id) AS n FROM orders
                WHERE status != 'cancelled' AND strftime('%Y-%m', created_at) = ?
                """,
                (_ms,),
            )
            _mom_counts[_ms] = _row_n["n"] if _row_n else 0
        _mom_series = []
        for _i in range(1, len(_mom_months)):
            _prev_m, _cur_m = _mom_months[_i - 1], _mom_months[_i]
            _prev_n, _cur_n = _mom_counts[_prev_m], _mom_counts[_cur_m]
            _pct = round(((_cur_n - _prev_n) / _prev_n) * 100, 2) if _prev_n else None
            _mom_series.append(
                {"month": _cur_m, "active_users": _cur_n, "pct_change_from_prior_month": _pct}
            )
        tasks["sqlreact-mom-active-users"] = {
            "type": "deterministic-computed",
            "prompt": TASKS["sqlreact-mom-active-users"],
            "expected": {"monthly_active_users": _mom_series},
        }

        _integrity_rows = _rows(
            conn,
            """
            SELECT o.id AS order_id, ROUND(o.total_amount, 2) AS recorded_total,
                   ROUND(COALESCE(
                       (SELECT SUM(oi.seats * oi.unit_price) FROM order_items oi WHERE oi.order_id = o.id),
                       0
                   ), 2) AS computed_total
            FROM orders o
            """,
        )
        _mismatches = [
            r for r in _integrity_rows if abs(r["recorded_total"] - r["computed_total"]) > 0.01
        ]
        tasks["sqlreact-data-integrity-check"] = {
            "type": "deterministic-computed",
            "prompt": TASKS["sqlreact-data-integrity-check"],
            "expected": {"mismatch_count": len(_mismatches), "mismatches": _mismatches},
        }

        tasks["sqlreact-city-subscription-value"] = {
            "type": "deterministic-sql",
            "prompt": TASKS["sqlreact-city-subscription-value"],
            "expected": _rows(
                conn,
                """
                WITH cust_value AS (
                    SELECT c.city, c.id, SUM(o.total_amount) AS value
                    FROM customers c
                    JOIN orders o ON o.customer_id = c.id
                    WHERE o.status != 'cancelled'
                    GROUP BY c.id
                )
                SELECT city, ROUND(AVG(value), 2) AS avg_subscription_value_per_user,
                       COUNT(*) AS user_count
                FROM cust_value
                GROUP BY city
                ORDER BY avg_subscription_value_per_user DESC
                LIMIT 3
                """,
            ),
        }

        tasks["sqlreact-early-cohort-comparison"] = {
            "type": "deterministic-sql",
            "prompt": TASKS["sqlreact-early-cohort-comparison"],
            "expected": _row(
                conn,
                """
                WITH earliest AS (SELECT MIN(created_at) AS min_created FROM customers),
                cust_value AS (
                    SELECT customer_id, SUM(total_amount) AS value
                    FROM orders WHERE status != 'cancelled'
                    GROUP BY customer_id
                )
                SELECT
                    ROUND(SUM(CASE WHEN c.created_at <= datetime(e.min_created, '+90 day')
                        THEN COALESCE(v.value, 0) ELSE 0 END), 2) AS early_cohort_value,
                    ROUND(SUM(CASE WHEN c.created_at > datetime(e.min_created, '+90 day')
                        THEN COALESCE(v.value, 0) ELSE 0 END), 2) AS rest_value
                FROM customers c
                CROSS JOIN earliest e
                LEFT JOIN cust_value v ON v.customer_id = c.id
                """,
            ),
        }

        _review_rows = _rows(
            conn,
            """
            SELECT product_id, rating, created_at FROM reviews
            ORDER BY product_id, created_at ASC
            """,
        )
        _by_product: dict[int, list[dict[str, Any]]] = {}
        for _r in _review_rows:
            _by_product.setdefault(_r["product_id"], []).append(_r)
        _trend_results = []
        for _pid, _revs in _by_product.items():
            if len(_revs) < 6:
                continue
            _split = len(_revs) // 2
            _earlier, _recent = _revs[:_split], _revs[_split:]
            _earlier_avg = round(sum(r["rating"] for r in _earlier) / len(_earlier), 2)
            _recent_avg = round(sum(r["rating"] for r in _recent) / len(_recent), 2)
            if _recent_avg - _earlier_avg >= 0.5:
                _name_row = _row(conn, "SELECT name FROM products WHERE id = ?", (_pid,))
                _trend_results.append(
                    {
                        "module_name": _name_row["name"] if _name_row else None,
                        "earlier_half_avg_rating": _earlier_avg,
                        "recent_half_avg_rating": _recent_avg,
                    }
                )
        _trend_results.sort(
            key=lambda x: (
                -(x["recent_half_avg_rating"] - x["earlier_half_avg_rating"]),
                x["module_name"],
            )
        )
        tasks["sqlreact-rating-trend"] = {
            "type": "deterministic-computed",
            "prompt": TASKS["sqlreact-rating-trend"],
            "expected": _trend_results,
        }

        # ── enterprise-sql-codemode ───────────────────────────────────────
        _top5_reviewed = _rows(
            conn,
            """
            SELECT p.id, p.name AS module_name, COUNT(r.id) AS review_count
            FROM products p JOIN reviews r ON r.product_id = p.id
            GROUP BY p.id ORDER BY review_count DESC, module_name ASC LIMIT 5
            """,
        )
        _rating_dist = []
        for _m in _top5_reviewed:
            _counts = _rows(
                conn,
                "SELECT rating, COUNT(*) AS n FROM reviews WHERE product_id = ? GROUP BY rating",
                (_m["id"],),
            )
            _star_counts = {str(i): 0 for i in range(1, 6)}
            for _c in _counts:
                _star_counts[str(_c["rating"])] = _c["n"]
            _rating_dist.append(
                {
                    "module_name": _m["module_name"],
                    "review_count": _m["review_count"],
                    "rating_distribution": _star_counts,
                }
            )
        tasks["sqlcodemode-rating-distribution-top5"] = {
            "type": "deterministic-computed",
            "prompt": TASKS["sqlcodemode-rating-distribution-top5"],
            "expected": _rating_dist,
        }

        _corr_pairs = _rows(
            conn,
            """
            SELECT p.annual_license_usd AS price, AVG(r.rating) AS avg_rating
            FROM products p JOIN reviews r ON r.product_id = p.id
            GROUP BY p.id HAVING COUNT(r.id) >= 3
            """,
        )
        _corr_xs = [p["price"] for p in _corr_pairs]
        _corr_ys = [p["avg_rating"] for p in _corr_pairs]
        try:
            _correlation = (
                round(statistics.correlation(_corr_xs, _corr_ys), 3) if len(_corr_xs) >= 2 else None
            )
        except statistics.StatisticsError:
            _correlation = None
        tasks["sqlcodemode-price-rating-correlation"] = {
            "type": "deterministic-computed",
            "prompt": TASKS["sqlcodemode-price-rating-correlation"],
            "expected": {"pearson_correlation": _correlation, "sample_size": len(_corr_xs)},
        }

        _delivered_amounts = [
            r["total_amount"]
            for r in _rows(conn, "SELECT total_amount FROM orders WHERE status = 'delivered'")
        ]
        _mean_amt = statistics.fmean(_delivered_amounts)
        _stdev_amt = statistics.pstdev(_delivered_amounts)
        _outlier_threshold = _mean_amt + 2 * _stdev_amt
        tasks["sqlcodemode-subscription-outliers"] = {
            "type": "deterministic-computed",
            "prompt": TASKS["sqlcodemode-subscription-outliers"],
            "expected": {
                "mean": round(_mean_amt, 2),
                "stdev": round(_stdev_amt, 2),
                "threshold": round(_outlier_threshold, 2),
                "outliers": _rows(
                    conn,
                    """
                    SELECT o.id AS order_id, c.full_name AS customer_name, o.total_amount
                    FROM orders o
                    JOIN customers c ON c.id = o.customer_id
                    WHERE o.status = 'delivered' AND o.total_amount > ?
                    ORDER BY o.total_amount DESC
                    """,
                    (_outlier_threshold,),
                ),
            },
        }

        _spend_rows = _rows(
            conn,
            """
            SELECT o.customer_id, strftime('%Y-%m', o.created_at) AS month, SUM(o.total_amount) AS spend
            FROM orders o WHERE o.status != 'cancelled'
            GROUP BY o.customer_id, month
            """,
        )
        _spend_by_customer: dict[int, dict[str, float]] = {}
        for _r in _spend_rows:
            _spend_by_customer.setdefault(_r["customer_id"], {})[_r["month"]] = _r["spend"]

        def _month_index(ms: str) -> int:
            y, m = ms.split("-")
            return int(y) * 12 + int(m)

        _best_jump: dict[str, Any] | None = None
        for _cid, _months in _spend_by_customer.items():
            _sorted_months = sorted(_months.keys(), key=_month_index)
            for _i in range(1, len(_sorted_months)):
                _prev_m, _cur_m = _sorted_months[_i - 1], _sorted_months[_i]
                if _month_index(_cur_m) - _month_index(_prev_m) != 1:
                    continue
                _increase = _months[_cur_m] - _months[_prev_m]
                if _best_jump is None or _increase > _best_jump["increase"]:
                    _best_jump = {
                        "customer_id": _cid,
                        "prev_month": _prev_m,
                        "cur_month": _cur_m,
                        "increase": round(_increase, 2),
                    }
        if _best_jump:
            _name_row = _row(
                conn, "SELECT full_name FROM customers WHERE id = ?", (_best_jump["customer_id"],)
            )
            _best_jump["customer_name"] = _name_row["full_name"] if _name_row else None
        tasks["sqlcodemode-customer-spend-jump"] = {
            "type": "deterministic-computed",
            "prompt": TASKS["sqlcodemode-customer-spend-jump"],
            "expected": _best_jump,
        }

        _cats = _rows(conn, "SELECT id, name FROM categories")
        _cv_results = []
        for _cat in _cats:
            _prices = [
                r["annual_license_usd"]
                for r in _rows(
                    conn,
                    "SELECT annual_license_usd FROM products WHERE category_id = ?",
                    (_cat["id"],),
                )
            ]
            _mean_p = statistics.fmean(_prices) if _prices else 0
            _stdev_p = statistics.pstdev(_prices) if _prices else 0
            _cv = round(_stdev_p / _mean_p, 4) if _mean_p else None
            _cv_results.append({"business_function": _cat["name"], "coefficient_of_variation": _cv})
        _cv_valid = sorted(
            (r for r in _cv_results if r["coefficient_of_variation"] is not None),
            key=lambda r: r["coefficient_of_variation"],
        )
        tasks["sqlcodemode-price-consistency-by-function"] = {
            "type": "deterministic-computed",
            "prompt": TASKS["sqlcodemode-price-consistency-by-function"],
            "expected": {
                "by_function": _cv_valid,
                "most_consistent": _cv_valid[0] if _cv_valid else None,
            },
        }

        _cadence_rows = _rows(
            conn,
            """
            SELECT customer_id, created_at FROM orders
            WHERE status != 'cancelled'
            ORDER BY customer_id, created_at ASC
            """,
        )
        _cadence_by_customer: dict[int, list[str]] = {}
        for _r in _cadence_rows:
            _cadence_by_customer.setdefault(_r["customer_id"], []).append(_r["created_at"])
        _cadences = []
        for _cid, _dates in _cadence_by_customer.items():
            if len(_dates) < 3:
                continue
            _dts = [datetime.fromisoformat(d) for d in _dates]
            _gaps = [(_dts[i] - _dts[i - 1]).total_seconds() / 86400 for i in range(1, len(_dts))]
            _cadences.append(
                {
                    "customer_id": _cid,
                    "avg_days_between_subscriptions": round(sum(_gaps) / len(_gaps), 2),
                    "subscription_count": len(_dates),
                }
            )
        _cadences.sort(key=lambda x: x["avg_days_between_subscriptions"])
        _cadence_top3 = _cadences[:3]
        for _c in _cadence_top3:
            _name_row = _row(
                conn, "SELECT full_name FROM customers WHERE id = ?", (_c["customer_id"],)
            )
            _c["customer_name"] = _name_row["full_name"] if _name_row else None
        tasks["sqlcodemode-subscription-cadence"] = {
            "type": "deterministic-computed",
            "prompt": TASKS["sqlcodemode-subscription-cadence"],
            "expected": _cadence_top3,
        }

        _quality_mods = _rows(
            conn,
            """
            SELECT p.name AS module_name, p.active_deployments, AVG(r.rating) AS avg_rating
            FROM products p JOIN reviews r ON r.product_id = p.id
            GROUP BY p.id
            """,
        )
        _quality_scored = []
        for _m in _quality_mods:
            _score = _m["avg_rating"] * math.log(_m["active_deployments"] + 1)
            _quality_scored.append(
                {
                    "module_name": _m["module_name"],
                    "avg_rating": round(_m["avg_rating"], 2),
                    "active_deployments": _m["active_deployments"],
                    "weighted_score": round(_score, 3),
                }
            )
        _quality_scored.sort(key=lambda x: x["weighted_score"], reverse=True)
        tasks["sqlcodemode-weighted-quality-score"] = {
            "type": "deterministic-computed",
            "prompt": TASKS["sqlcodemode-weighted-quality-score"],
            "expected": _quality_scored[:3],
        }

        _all_deployments = [
            r["active_deployments"] for r in _rows(conn, "SELECT active_deployments FROM products")
        ]
        _median_dep = statistics.median(_all_deployments)
        _unreviewed_rows = _rows(
            conn,
            """
            SELECT p.name AS module_name, c.name AS business_function, p.active_deployments
            FROM products p
            JOIN categories c ON c.id = p.category_id
            LEFT JOIN reviews r ON r.product_id = p.id
            GROUP BY p.id
            HAVING COUNT(r.id) = 0
            """,
        )
        _unreviewed_below_median = sorted(
            (r for r in _unreviewed_rows if r["active_deployments"] < _median_dep),
            key=lambda r: (r["active_deployments"], r["module_name"]),
        )
        tasks["sqlcodemode-unreviewed-below-median"] = {
            "type": "deterministic-computed",
            "prompt": TASKS["sqlcodemode-unreviewed-below-median"],
            "expected": {
                "median_active_deployments": _median_dep,
                "modules": _unreviewed_below_median,
            },
        }

        _top5_gold = _rows(
            conn,
            """
            SELECT c.id, c.full_name,
                   ROUND(COALESCE(SUM(CASE WHEN o.status != 'cancelled' THEN o.total_amount END), 0), 2)
                     AS lifetime_value
            FROM customers c
            LEFT JOIN orders o ON o.customer_id = c.id
            WHERE c.tier = 'gold'
            GROUP BY c.id
            ORDER BY lifetime_value DESC, c.full_name ASC
            LIMIT 5
            """,
        )
        _cat_sets: dict[int, set[str]] = {}
        for _cust in _top5_gold:
            _cat_rows = _rows(
                conn,
                """
                SELECT DISTINCT cat.name AS business_function
                FROM orders o
                JOIN order_items oi ON oi.order_id = o.id
                JOIN products p ON p.id = oi.product_id
                JOIN categories cat ON cat.id = p.category_id
                WHERE o.customer_id = ? AND o.status != 'cancelled'
                """,
                (_cust["id"],),
            )
            _cat_sets[_cust["id"]] = {r["business_function"] for r in _cat_rows}
        _best_pair: dict[str, Any] | None = None
        for _i in range(len(_top5_gold)):
            for _j in range(_i + 1, len(_top5_gold)):
                _a, _b = _top5_gold[_i], _top5_gold[_j]
                _set_a, _set_b = _cat_sets[_a["id"]], _cat_sets[_b["id"]]
                _union = _set_a | _set_b
                _inter = _set_a & _set_b
                _jaccard = round(len(_inter) / len(_union), 3) if _union else 0.0
                _pair_ids = (_a["id"], _b["id"])
                if _best_pair is None or _jaccard > _best_pair["jaccard_similarity"]:
                    _best_pair = {
                        "customer_a": _a["full_name"],
                        "customer_b": _b["full_name"],
                        "jaccard_similarity": _jaccard,
                        "_pair_ids": _pair_ids,
                    }
        if _best_pair:
            _best_pair.pop("_pair_ids", None)
        tasks["sqlcodemode-gold-category-overlap"] = {
            "type": "deterministic-computed",
            "prompt": TASKS["sqlcodemode-gold-category-overlap"],
            "expected": _best_pair,
        }

        _sim_months = _trailing_complete_months(max_created_at, 6)
        _sim_series = []
        for _ms in _sim_months:
            _sim_row = _row(
                conn,
                """
                SELECT ROUND(SUM(oi.seats * oi.unit_price), 2) AS actual_revenue,
                       ROUND(SUM(2 * oi.unit_price), 2) AS simulated_revenue
                FROM order_items oi
                JOIN orders o ON o.id = oi.order_id
                WHERE o.status != 'cancelled' AND strftime('%Y-%m', o.created_at) = ?
                """,
                (_ms,),
            )
            _sim_series.append(
                {
                    "month": _ms,
                    "actual_revenue": (_sim_row["actual_revenue"] or 0) if _sim_row else 0,
                    "simulated_2_seat_revenue": (_sim_row["simulated_revenue"] or 0)
                    if _sim_row
                    else 0,
                }
            )
        tasks["sqlcodemode-seat-normalization-simulation"] = {
            "type": "deterministic-computed",
            "prompt": TASKS["sqlcodemode-seat-normalization-simulation"],
            "expected": {"by_month": _sim_series},
        }

        _momentum_months = _trailing_complete_months(max_created_at, 12)
        _most_recent_month = _momentum_months[-1]
        _momentum_results = []
        for _cat in _cats:
            _monthly_rev: dict[str, float] = {}
            for _ms in _momentum_months:
                _mrow = _row(
                    conn,
                    """
                    SELECT ROUND(SUM(oi.seats * oi.unit_price), 2) AS revenue
                    FROM order_items oi
                    JOIN orders o ON o.id = oi.order_id
                    JOIN products p ON p.id = oi.product_id
                    WHERE p.category_id = ? AND o.status != 'cancelled'
                      AND strftime('%Y-%m', o.created_at) = ?
                    """,
                    (_cat["id"], _ms),
                )
                _monthly_rev[_ms] = (_mrow["revenue"] or 0.0) if _mrow else 0.0
            _trailing_avg = sum(_monthly_rev.values()) / len(_momentum_months)
            _most_recent_rev = _monthly_rev[_most_recent_month]
            _ratio = round(_most_recent_rev / _trailing_avg, 3) if _trailing_avg else None
            _momentum_results.append(
                {
                    "business_function": _cat["name"],
                    "most_recent_month_revenue": round(_most_recent_rev, 2),
                    "trailing_12mo_avg_revenue": round(_trailing_avg, 2),
                    "momentum_ratio": _ratio,
                }
            )
        _momentum_valid = [r for r in _momentum_results if r["momentum_ratio"] is not None]
        _highest_momentum = (
            max(_momentum_valid, key=lambda r: r["momentum_ratio"]) if _momentum_valid else None
        )
        tasks["sqlcodemode-revenue-momentum"] = {
            "type": "deterministic-computed",
            "prompt": TASKS["sqlcodemode-revenue-momentum"],
            "expected": {"by_function": _momentum_results, "highest_momentum": _highest_momentum},
        }

        _gold_customers = _rows(conn, "SELECT id, full_name FROM customers WHERE tier = 'gold'")
        _engagement_scores = []
        for _cust in _gold_customers:
            _cid = _cust["id"]
            _lv_row = _row(
                conn,
                "SELECT COALESCE(SUM(total_amount), 0) AS v FROM orders"
                " WHERE customer_id = ? AND status != 'cancelled'",
                (_cid,),
            )
            _lifetime_value = (_lv_row["v"] or 0.0) if _lv_row else 0.0
            _review_row = _row(
                conn, "SELECT COUNT(*) AS n FROM reviews WHERE customer_id = ?", (_cid,)
            )
            _review_count = (_review_row["n"] or 0) if _review_row else 0
            _recent_row = _row(
                conn,
                "SELECT MAX(created_at) AS m FROM orders"
                " WHERE customer_id = ? AND status != 'cancelled'",
                (_cid,),
            )
            _recent_date = _recent_row["m"] if _recent_row else None
            _recency_bonus = 0
            if _recent_date and max_created_at:
                _days_since = (
                    datetime.fromisoformat(max_created_at) - datetime.fromisoformat(_recent_date)
                ).days
                if _days_since <= 90:
                    _recency_bonus = 100
            _score = round(_lifetime_value / 1000 + _review_count * 50 + _recency_bonus, 2)
            _engagement_scores.append(
                {
                    "customer_name": _cust["full_name"],
                    "lifetime_subscription_value": round(_lifetime_value, 2),
                    "number_of_reviews_written": _review_count,
                    "recency_bonus": _recency_bonus,
                    "engagement_score": _score,
                }
            )
        _engagement_scores.sort(key=lambda x: (-x["engagement_score"], x["customer_name"]))
        tasks["sqlcodemode-composite-engagement-score"] = {
            "type": "deterministic-computed",
            "prompt": TASKS["sqlcodemode-composite-engagement-score"],
            "expected": _engagement_scores[:5],
        }

        # ── minimal: pure computation, no database access ─────────────────
        tasks["minimal-percentage-discount"] = {
            "type": "deterministic-computed",
            "prompt": TASKS["minimal-percentage-discount"],
            "expected": {"discounted_price": round(1200 * 0.85, 2)},
        }
        tasks["minimal-compound-interest"] = {
            "type": "deterministic-computed",
            "prompt": TASKS["minimal-compound-interest"],
            "expected": {"balance_after_2_years": round(5000 * (1 + 0.06 / 12) ** (12 * 2), 2)},
        }
        _list_stats_data = [12, 45, 7, 23, 56, 34, 19, 8]
        tasks["minimal-list-statistics"] = {
            "type": "deterministic-computed",
            "prompt": TASKS["minimal-list-statistics"],
            "expected": {
                "mean": round(statistics.mean(_list_stats_data), 2),
                "median": round(statistics.median(_list_stats_data), 2),
                "sample_stdev": round(statistics.stdev(_list_stats_data), 2),
            },
        }
        _rev_string = "DecisionIntelligence"
        tasks["minimal-string-reversal-vowels"] = {
            "type": "deterministic-computed",
            "prompt": TASKS["minimal-string-reversal-vowels"],
            "expected": {
                "reversed_string": _rev_string[::-1],
                "vowel_count": sum(1 for c in _rev_string.lower() if c in "aeiou"),
            },
        }
        tasks["minimal-date-formatting"] = {
            "type": "deterministic-computed",
            "prompt": TASKS["minimal-date-formatting"],
            "expected": {"formatted_date": "November 3, 2026"},
        }
        tasks["minimal-fizzbuzz-range"] = {
            "type": "deterministic-computed",
            "prompt": TASKS["minimal-fizzbuzz-range"],
            "expected": {"divisible_by_3_and_5": [i for i in range(1, 101) if i % 15 == 0]},
        }
        _caesar_word = "AGENT"
        tasks["minimal-caesar-cipher"] = {
            "type": "deterministic-computed",
            "prompt": TASKS["minimal-caesar-cipher"],
            "expected": {
                "encoded_word": "".join(chr((ord(c) - 65 + 3) % 26 + 65) for c in _caesar_word)
            },
        }
        _palindrome_phrase = "A man a plan a canal Panama"
        _palindrome_cleaned = "".join(c.lower() for c in _palindrome_phrase if c.isalnum())
        tasks["minimal-palindrome-check"] = {
            "type": "deterministic-computed",
            "prompt": TASKS["minimal-palindrome-check"],
            "expected": {
                "is_palindrome": _palindrome_cleaned == _palindrome_cleaned[::-1],
                "cleaned_string": _palindrome_cleaned,
            },
        }
        _gcd_val = math.gcd(48, 180)
        tasks["minimal-gcd-lcm"] = {
            "type": "deterministic-computed",
            "prompt": TASKS["minimal-gcd-lcm"],
            "expected": {"gcd": _gcd_val, "lcm": 48 * 180 // _gcd_val},
        }
        _word_count_sentence = "The quick brown fox jumps over the lazy dog and the fox runs away"
        _words = _word_count_sentence.split()
        tasks["minimal-word-count-unique"] = {
            "type": "deterministic-computed",
            "prompt": TASKS["minimal-word-count-unique"],
            "expected": {
                "total_words": len(_words),
                "unique_words": len({w.lower() for w in _words}),
            },
        }
        tasks["minimal-unit-conversion"] = {
            "type": "deterministic-computed",
            "prompt": TASKS["minimal-unit-conversion"],
            "expected": {"miles_per_hour": round(82 * 0.621371, 2)},
        }
        _marble_gcd = math.gcd(7, 10)
        tasks["minimal-marble-probability"] = {
            "type": "deterministic-computed",
            "prompt": TASKS["minimal-marble-probability"],
            "expected": {
                "fraction": f"{7 // _marble_gcd}/{10 // _marble_gcd}",
                "percentage": round(7 / 10 * 100, 1),
            },
        }

        # ── minimal: conversational small talk / FAQ ────────────────────────
        # No factual claim to check, so `expected` is None like external-dynamic
        # tasks. `type` is "conversational" rather than "external-dynamic" to
        # keep the reason for exclusion from strict scoring accurate: these
        # aren't unscorable because of live/volatile external state, they're
        # unscorable because there's no single correct reply to a greeting.
        for _key, _note in [
            (
                "minimal-greeting-howareyou",
                "A friendly, brief reply to a greeting; no tool call or business "
                "data is applicable.",
            ),
            (
                "minimal-greeting-whatsup",
                "A friendly, brief reply to casual small talk; no tool call or "
                "business data is applicable.",
            ),
            (
                "minimal-faq-capabilities",
                "A brief summary of the assistant's own capabilities; no "
                "customer/product/order lookup is applicable.",
            ),
        ]:
            tasks[_key] = {
                "type": "conversational",
                "prompt": TASKS[_key],
                "expected": None,
                "notes": _note,
            }

        return {
            "generated_at": datetime.now(UTC).isoformat(),
            "db_path": str(DB_PATH),
            "max_order_created_at": max_created_at,
            "notes": [
                "Ground truth is deterministic for seeded SQLite data.",
                "Metric scoring can compare model outputs against expected fields/rows per task.",
                "hn-research is external-dynamic and excluded from strict deterministic scoring.",
                "minimal-greeting-*/minimal-faq-* are conversational and excluded from strict "
                "deterministic scoring — there is no single correct reply to a greeting.",
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
