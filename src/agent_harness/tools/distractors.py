"""Distractor tools — plausible-sounding but incorrect/irrelevant tools used to test tool
selection accuracy and hallucination resistance at a large (120-tool) tool-surface scale.

Every function name in `DISTRACTOR_TOOLS` is one an agent should *never* need to call to
correctly answer any task in `tasks/builtins.py`. They fall into five bait categories:

  legacy    — renamed/old aliases of a real tool that silently return stale, incomplete, or
              differently-computed data (e.g. wrong price basis, truncated results).
  external  — plausible enterprise-assistant actions with no data backing at all
              (send email, book travel, check weather...). Always return "unavailable".
  trap      — real DB-backed tools whose name implies one thing but whose behavior silently
              ignores an argument, drops precision, or narrows scope compared to what the name
              promises.
  lookup    — real DB-backed tools keyed by name/email/free text instead of ID, which is
              ambiguous or brittle against this dataset's duplicate names / partial matches.
  synthetic — "AI-sounding" analytics (churn prediction, NPS, sentiment, industry benchmarks...)
              that this dataset has no real underlying signal for. Returns a deterministic but
              non-authoritative synthetic value with no real data backing whatsoever.

`tool_selection_benchmark.py` treats *any* call to a name in `DISTRACTOR_TOOLS` as a
tool-hallucination / bad-tool-selection event, independent of what the function returns.
"""

from __future__ import annotations

import random
from typing import Any

from agent_harness.db.schema import get_connection


def _rows(sql: str, *params) -> list[dict[str, Any]]:
    with get_connection() as conn:
        rows = conn.execute(sql, params).fetchall()
        return [dict(r) for r in rows]


def _row(sql: str, *params) -> dict[str, Any] | None:
    with get_connection() as conn:
        row = conn.execute(sql, params).fetchone()
        return dict(row) if row else None


def _unavailable(capability: str) -> dict[str, Any]:
    return {
        "status": "unavailable",
        "message": f"{capability} is not connected in this environment.",
    }


def _pseudo(seed_key: Any, lo: float, hi: float) -> float:
    """Deterministic pseudo-random value in [lo, hi], stable across runs for the same key."""
    return round(random.Random(f"distractor:{seed_key}").uniform(lo, hi), 2)


# ═══════════════════════════════════════════════════════════════════════════
# legacy — renamed aliases returning stale/incomplete/differently-computed data
# ═══════════════════════════════════════════════════════════════════════════

def get_customer_v2(customer_id: int) -> dict[str, Any] | None:
    """Get a business user's profile (v2 endpoint).

    Args:
        customer_id: The business user's integer ID.
    """
    return _row(
        "SELECT id, full_name, email, city, country, tier FROM customers WHERE id = ?",
        customer_id,
    )


def get_product_legacy(product_id: int) -> dict[str, Any] | None:
    """Get analytics module details from the legacy catalogue snapshot.

    Args:
        product_id: The analytics module's integer ID.
    """
    row = _row(
        "SELECT id, name, description, annual_license_usd FROM products WHERE id = ?",
        product_id,
    )
    if row is None:
        return None
    row["annual_license_usd"] = round(row["annual_license_usd"] * 0.9, 2)
    return row


def list_products_old(category: str = "") -> list[dict[str, Any]]:
    """List analytics modules from the old catalogue index, optionally by business function.

    Args:
        category: Filter by business function name (partial match). Empty = all.
    """
    where = "c.name LIKE ?" if category else "1=1"
    params = [f"%{category}%"] if category else []
    return _rows(
        f"""
        SELECT p.id, p.name, c.name AS business_function
        FROM products p JOIN categories c ON c.id = p.category_id
        WHERE {where} ORDER BY p.id LIMIT 5
        """,
        *params,
    )


def search_orders_deprecated(customer_id: int) -> list[dict[str, Any]]:
    """Search a business user's subscriptions (deprecated — use get_customer_orders).

    Args:
        customer_id: The business user's integer ID.
    """
    return _rows(
        "SELECT id, status, total_amount FROM orders WHERE customer_id = ? LIMIT 3",
        customer_id,
    )


def get_sales_report_v1(start_date: str, end_date: str) -> dict[str, Any]:
    """Legacy sales report (v1 formula) for a date range.

    Args:
        start_date: Period start, e.g. '2024-01-01'.
        end_date: Period end, e.g. '2024-03-31'.
    """
    return _row(
        """
        SELECT ROUND(SUM(oi.seats), 2) AS total_revenue
        FROM order_items oi JOIN orders o ON o.id = oi.order_id
        WHERE o.created_at BETWEEN ? AND ?
        """,
        start_date,
        end_date + "T23:59:59",
    ) or {"total_revenue": 0}


def get_customer_orders_v1(customer_id: int) -> list[dict[str, Any]]:
    """Get a business user's subscriptions (v1 endpoint, includes all statuses unmarked).

    Args:
        customer_id: The business user's integer ID.
    """
    return _rows(
        "SELECT id, total_amount, created_at FROM orders WHERE customer_id = ?", customer_id
    )


def get_revenue_summary_legacy(year: int) -> list[dict[str, Any]]:
    """Legacy revenue summary for a year, grouped by quarter (mislabeled 'monthly' in some
    older client integrations).

    Args:
        year: Four-digit year.
    """
    return _rows(
        """
        SELECT 'Q' || ((CAST(strftime('%m', created_at) AS INTEGER) - 1) / 3 + 1) AS month,
               ROUND(SUM(total_amount), 2) AS revenue
        FROM orders
        WHERE strftime('%Y', created_at) = ? AND status != 'cancelled'
        GROUP BY month
        """,
        str(year),
    )


def get_top_products_cached(limit: int = 10) -> list[dict[str, Any]]:
    """Return the top analytics modules from last quarter's cached leaderboard snapshot.

    Args:
        limit: Requested row count (the cache snapshot is fixed-size and may not honor this).
    """
    return _rows(
        "SELECT name AS module_name, active_deployments FROM products ORDER BY id LIMIT 10"
    )


def get_employee_record(employee_id: int) -> dict[str, Any] | None:
    """Get an employee record from the legacy HR system export.

    Args:
        employee_id: The employee's integer ID.
    """
    return _row(
        "SELECT id, full_name, title, salary_usd FROM employees WHERE id = ?", employee_id
    )


def get_supplier_info(supplier_id: int) -> dict[str, Any] | None:
    """Get supplier info from the legacy vendor master file.

    Args:
        supplier_id: The supplier's integer ID.
    """
    row = _row("SELECT id, name, country, rating FROM suppliers WHERE id = ?", supplier_id)
    if row is not None:
        row["rating"] = float(int(row["rating"]))
    return row


# ═══════════════════════════════════════════════════════════════════════════
# external — plausible assistant actions with zero data backing
# ═══════════════════════════════════════════════════════════════════════════

def send_email_notification(to: str, subject: str, body: str) -> dict[str, Any]:
    """Send an email notification to a recipient.

    Args:
        to: Recipient email address.
        subject: Email subject line.
        body: Email body text.
    """
    return _unavailable("Outbound email")


def create_calendar_invite(title: str, start_time: str, attendees: str = "") -> dict[str, Any]:
    """Create a calendar invite/meeting.

    Args:
        title: Meeting title.
        start_time: ISO-8601 start time.
        attendees: Comma-separated attendee emails.
    """
    return _unavailable("Calendar integration")


def schedule_meeting(topic: str, participants: str = "", duration_minutes: int = 30) -> dict[str, Any]:
    """Schedule a meeting with participants.

    Args:
        topic: Meeting topic.
        participants: Comma-separated participant names/emails.
        duration_minutes: Meeting length in minutes.
    """
    return _unavailable("Meeting scheduling")


def get_weather_forecast(city: str) -> dict[str, Any]:
    """Get the weather forecast for a city.

    Args:
        city: City name.
    """
    return _unavailable("Weather data")


def translate_text(text: str, target_language: str) -> dict[str, Any]:
    """Translate text into another language.

    Args:
        text: Text to translate.
        target_language: Target language name or code.
    """
    return _unavailable("Translation service")


def generate_pdf_report(title: str, content: str = "") -> dict[str, Any]:
    """Generate a PDF report document.

    Args:
        title: Report title.
        content: Report body content.
    """
    return _unavailable("PDF generation")


def post_to_slack(channel: str, message: str) -> dict[str, Any]:
    """Post a message to a Slack channel.

    Args:
        channel: Slack channel name.
        message: Message text.
    """
    return _unavailable("Slack integration")


def create_jira_ticket(project: str, summary: str, description: str = "") -> dict[str, Any]:
    """Create a Jira ticket in a project.

    Args:
        project: Jira project key.
        summary: Ticket summary.
        description: Ticket description.
    """
    return _unavailable("Jira integration")


def send_sms_alert(phone_number: str, message: str) -> dict[str, Any]:
    """Send an SMS text alert.

    Args:
        phone_number: Recipient phone number.
        message: Message text.
    """
    return _unavailable("SMS gateway")


def book_travel(destination: str, start_date: str, end_date: str) -> dict[str, Any]:
    """Book travel arrangements for a trip.

    Args:
        destination: Destination city.
        start_date: ISO-8601 trip start date.
        end_date: ISO-8601 trip end date.
    """
    return _unavailable("Travel booking")


# ═══════════════════════════════════════════════════════════════════════════
# trap — real tools whose name overpromises vs. their actual (narrower) behavior
# ═══════════════════════════════════════════════════════════════════════════

def get_top_selling_products_by_region(region: str, limit: int = 10) -> list[dict[str, Any]]:
    """Return the top-selling analytics modules for a specific region.

    Args:
        region: Region name (e.g. 'US', 'EMEA', 'APAC').
        limit: How many modules to return.
    """
    # NOTE: this dataset has no per-order region column; silently falls back to global figures.
    return _rows(
        """
        SELECT p.name AS module_name, COUNT(DISTINCT oi.order_id) AS activation_count
        FROM order_items oi JOIN orders o ON o.id = oi.order_id JOIN products p ON p.id = oi.product_id
        WHERE o.status != 'cancelled'
        GROUP BY p.id ORDER BY activation_count DESC LIMIT ?
        """,
        limit,
    )


def get_customer_orders_summary(customer_id: int) -> dict[str, Any] | None:
    """Get a summary of a business user's subscriptions.

    Args:
        customer_id: The business user's integer ID.
    """
    return _row("SELECT COUNT(*) AS order_count FROM orders WHERE customer_id = ?", customer_id)


def get_revenue_forecast(months_ahead: int = 3) -> dict[str, Any]:
    """Forecast subscription revenue for the next N months.

    Args:
        months_ahead: How many months ahead to forecast.
    """
    last_month = _row(
        """
        SELECT ROUND(SUM(total_amount), 2) AS revenue
        FROM orders WHERE status != 'cancelled'
          AND created_at >= datetime((SELECT MAX(created_at) FROM orders), '-30 day')
        """
    )
    base = (last_month or {}).get("revenue") or 0.0
    return {"months_ahead": months_ahead, "forecasted_revenue": round(base * months_ahead, 2)}


def get_supplier_scorecard(supplier_id: int) -> dict[str, Any] | None:
    """Get a supplier's overall scorecard rating.

    Args:
        supplier_id: The supplier's integer ID.
    """
    return _row("SELECT id, rating AS scorecard FROM suppliers WHERE id = ?", supplier_id)


def get_employee_directory(department: str = "") -> list[dict[str, Any]]:
    """Get the employee directory, optionally filtered by department.

    Args:
        department: Partial department name match. Empty = all departments.
    """
    where = "d.name LIKE ?" if department else "1=1"
    params = [f"%{department}%"] if department else []
    return _rows(
        f"""
        SELECT e.full_name, e.title
        FROM employees e JOIN departments d ON d.id = e.department_id
        WHERE {where} AND e.is_active = 1
        """,
        *params,
    )


def get_campaign_summary(campaign_id: int) -> dict[str, Any] | None:
    """Get a summary of a marketing campaign.

    Args:
        campaign_id: The campaign's integer ID.
    """
    return _row("SELECT id, name, status, budget_usd FROM campaigns WHERE id = ?", campaign_id)


def get_ticket_summary(customer_id: int) -> dict[str, Any] | None:
    """Get a summary of a business user's support tickets.

    Args:
        customer_id: The business user's integer ID.
    """
    return _row(
        "SELECT COUNT(*) AS ticket_count FROM support_tickets WHERE customer_id = ?", customer_id
    )


def get_budget_summary(department: str) -> list[dict[str, Any]]:
    """Get a department's budget summary.

    Args:
        department: Exact department name.
    """
    # NOTE: always uses the current calendar year regardless of what the caller actually wants.
    from datetime import UTC, datetime

    year = datetime.now(UTC).year
    return _rows(
        """
        SELECT b.category, b.allocated_usd
        FROM budgets b JOIN departments d ON d.id = b.department_id
        WHERE d.name = ? AND b.year = ?
        """,
        department,
        year,
    )


def get_purchase_order_status(po_id: int) -> dict[str, Any] | None:
    """Get a purchase order's status.

    Args:
        po_id: The purchase order's integer ID.
    """
    return _row("SELECT id, status FROM purchase_orders WHERE id = ?", po_id)


def get_module_rating_summary(product_id: int) -> dict[str, Any] | None:
    """Get a rating summary for an analytics module.

    Args:
        product_id: The analytics module's integer ID.
    """
    row = _row(
        "SELECT ROUND(AVG(rating), 0) AS avg_rating FROM reviews WHERE product_id = ?", product_id
    )
    return row


def get_low_adoption_report(threshold: int = 30) -> list[dict[str, Any]]:
    """Get a report of analytics modules with low deployment adoption.

    Args:
        threshold: Deployment count warning level.
    """
    # NOTE: always uses a fixed threshold of 30, ignoring the argument.
    return _rows(
        "SELECT name AS module_name, active_deployments FROM products WHERE active_deployments <= 30"
    )


def get_customer_engagement_score(customer_id: int) -> dict[str, Any]:
    """Get a business user's overall engagement score.

    Args:
        customer_id: The business user's integer ID.
    """
    return {"customer_id": customer_id, "engagement_score": _pseudo(("engagement", customer_id), 20, 99)}


def get_quarterly_growth_rate(business_function: str) -> dict[str, Any]:
    """Get the quarter-over-quarter growth rate for a business function.

    Args:
        business_function: Business function name (e.g. 'Finance').
    """
    return {
        "business_function": business_function,
        "qoq_growth_rate_pct": _pseudo(("qoq", business_function), -8.0, 22.0),
    }


# ═══════════════════════════════════════════════════════════════════════════
# lookup — real tools keyed by name/email/free text instead of ID (ambiguous)
# ═══════════════════════════════════════════════════════════════════════════

def get_order_by_customer_name(customer_name: str) -> list[dict[str, Any]]:
    """Get subscriptions for a business user, looked up by name.

    Args:
        customer_name: The business user's full name (partial match).
    """
    return _rows(
        """
        SELECT o.id, o.status, o.total_amount
        FROM orders o JOIN customers c ON c.id = o.customer_id
        WHERE c.full_name LIKE ? LIMIT 5
        """,
        f"%{customer_name}%",
    )


def get_ticket_by_email(email: str) -> list[dict[str, Any]]:
    """Get support tickets for a business user, looked up by email.

    Args:
        email: The business user's email address (partial match).
    """
    return _rows(
        """
        SELECT t.id, t.subject, t.status
        FROM support_tickets t JOIN customers c ON c.id = t.customer_id
        WHERE c.email LIKE ? LIMIT 5
        """,
        f"%{email}%",
    )


def get_campaign_by_name(name: str) -> dict[str, Any] | None:
    """Get a marketing campaign, looked up by name.

    Args:
        name: Campaign name (partial match).
    """
    return _row("SELECT id, name, status FROM campaigns WHERE name LIKE ? LIMIT 1", f"%{name}%")


def get_supplier_by_company(company_name: str) -> dict[str, Any] | None:
    """Get a supplier, looked up by company name.

    Args:
        company_name: Supplier company name (partial match).
    """
    return _row("SELECT id, name, country FROM suppliers WHERE name LIKE ? LIMIT 1", f"%{company_name}%")


def get_employee_by_name(full_name: str) -> dict[str, Any] | None:
    """Get an employee, looked up by full name.

    Args:
        full_name: Employee's full name (partial match).
    """
    return _row("SELECT id, title FROM employees WHERE full_name LIKE ? LIMIT 1", f"%{full_name}%")


def get_product_by_title(title: str) -> dict[str, Any] | None:
    """Get an analytics module, looked up by title.

    Args:
        title: Module title/name (partial match).
    """
    return _row("SELECT id, name FROM products WHERE name LIKE ? LIMIT 1", f"%{title}%")


def get_department_by_label(label: str) -> dict[str, Any] | None:
    """Get a department, looked up by label.

    Args:
        label: Department label (must match exactly).
    """
    return _row("SELECT id, name, function FROM departments WHERE name = ?", label)


def get_budget_by_department_name(department_name: str, year: int) -> dict[str, Any] | None:
    """Get a department's budget total, looked up by department name.

    Args:
        department_name: Exact department name.
        year: Four-digit budget year.
    """
    return _row(
        """
        SELECT ROUND(SUM(b.allocated_usd), 2) AS total_allocated
        FROM budgets b JOIN departments d ON d.id = b.department_id
        WHERE d.name = ? AND b.year = ?
        """,
        department_name,
        year,
    )


def get_review_by_customer_and_product(customer_name: str, product_name: str) -> dict[str, Any] | None:
    """Get a user satisfaction rating, looked up by customer name and module name.

    Args:
        customer_name: Reviewer's full name (exact match).
        product_name: Analytics module name (exact match).
    """
    return _row(
        """
        SELECT r.rating, r.title
        FROM reviews r
        JOIN customers c ON c.id = r.customer_id
        JOIN products p ON p.id = r.product_id
        WHERE c.full_name = ? AND p.name = ?
        """,
        customer_name,
        product_name,
    )


def get_expense_by_description(keyword: str) -> dict[str, Any] | None:
    """Get an expense line item, looked up by description keyword.

    Args:
        keyword: Keyword to search for in the expense description.
    """
    return _row(
        "SELECT id, amount_usd, description FROM expenses WHERE description LIKE ? LIMIT 1",
        f"%{keyword}%",
    )


# ═══════════════════════════════════════════════════════════════════════════
# synthetic — "AI-sounding" analytics with no real underlying signal in this dataset
# ═══════════════════════════════════════════════════════════════════════════

def get_ai_recommendation(context: str) -> dict[str, Any]:
    """Get an AI-generated business recommendation for a given context.

    Args:
        context: Free-text description of the situation to get a recommendation for.
    """
    return {"context": context, "recommendation": "Prioritize the highest-revenue opportunity."}


def get_risk_score(entity_id: int) -> dict[str, Any]:
    """Get a general-purpose risk score for any entity ID in the system.

    Args:
        entity_id: The entity's integer ID.
    """
    return {"entity_id": entity_id, "risk_score": _pseudo(("risk", entity_id), 0, 100)}


def get_health_score(entity_type: str, entity_id: int) -> dict[str, Any]:
    """Get an overall health score for an account, module, or campaign.

    Args:
        entity_type: Type of entity ('customer', 'product', 'campaign').
        entity_id: The entity's integer ID.
    """
    return {
        "entity_type": entity_type,
        "entity_id": entity_id,
        "health_score": _pseudo(("health", entity_type, entity_id), 0, 100),
    }


def predict_churn(customer_id: int) -> dict[str, Any]:
    """Predict the likelihood a business user will churn (cancel all subscriptions).

    Args:
        customer_id: The business user's integer ID.
    """
    return {
        "customer_id": customer_id,
        "churn_probability": round(_pseudo(("churn", customer_id), 0, 100) / 100, 3),
    }


def get_nps_score(days: int = 90) -> dict[str, Any]:
    """Get the platform-wide Net Promoter Score over the last N days.

    Args:
        days: Look-back window in days.
    """
    return {"days": days, "nps": _pseudo(("nps", days), -20, 70)}


def get_market_benchmark(business_function: str) -> dict[str, Any]:
    """Get the external market benchmark performance for a business function.

    Args:
        business_function: Business function name.
    """
    return {
        "business_function": business_function,
        "benchmark_score": _pseudo(("benchmark", business_function), 40, 95),
    }


def get_industry_average(metric_name: str) -> dict[str, Any]:
    """Get the industry-average value for a named business metric.

    Args:
        metric_name: Metric name (e.g. 'subscription_revenue', 'churn_rate').
    """
    return {"metric_name": metric_name, "industry_average": _pseudo(("industry", metric_name), 1, 1000)}


def get_competitor_analysis(business_function: str) -> dict[str, Any]:
    """Get a competitive positioning analysis for a business function.

    Args:
        business_function: Business function name.
    """
    return {
        "business_function": business_function,
        "competitive_position": "above average",
    }


def get_sentiment_score(product_id: int) -> dict[str, Any]:
    """Get an aggregate sentiment score for an analytics module's user feedback.

    Args:
        product_id: The analytics module's integer ID.
    """
    return {"product_id": product_id, "sentiment_score": _pseudo(("sentiment", product_id), -1, 1)}


def get_anomaly_report(days: int = 30) -> dict[str, Any]:
    """Get a report of statistical anomalies detected across the platform in the last N days.

    Args:
        days: Look-back window in days.
    """
    return {"days": days, "anomalies_detected": int(_pseudo(("anomaly", days), 0, 5))}


def get_data_quality_score(table_name: str) -> dict[str, Any]:
    """Get a data quality score for a database table.

    Args:
        table_name: The table name to score.
    """
    return {"table_name": table_name, "quality_score": _pseudo(("dq", table_name), 70, 100)}


def get_audit_log(entity_id: int) -> dict[str, Any]:
    """Get the audit log of changes for any entity ID in the system.

    Args:
        entity_id: The entity's integer ID.
    """
    return {"entity_id": entity_id, "audit_entries": []}


def get_system_status() -> dict[str, Any]:
    """Get the current operational status of the platform's backend systems."""
    return {"status": "operational", "uptime_pct": 99.98}


def get_user_permissions(customer_id: int) -> dict[str, Any]:
    """Get the access permissions for a business user account.

    Args:
        customer_id: The business user's integer ID.
    """
    return {"customer_id": customer_id, "role": "standard_user", "permissions": ["read"]}


def get_api_usage(days: int = 30) -> dict[str, Any]:
    """Get platform API usage statistics over the last N days.

    Args:
        days: Look-back window in days.
    """
    return {"days": days, "api_calls": int(_pseudo(("api_usage", days), 1000, 500000))}


DISTRACTOR_TOOLS: frozenset[str] = frozenset(
    {
        # legacy
        "get_customer_v2",
        "get_product_legacy",
        "list_products_old",
        "search_orders_deprecated",
        "get_sales_report_v1",
        "get_customer_orders_v1",
        "get_revenue_summary_legacy",
        "get_top_products_cached",
        "get_employee_record",
        "get_supplier_info",
        # external
        "send_email_notification",
        "create_calendar_invite",
        "schedule_meeting",
        "get_weather_forecast",
        "translate_text",
        "generate_pdf_report",
        "post_to_slack",
        "create_jira_ticket",
        "send_sms_alert",
        "book_travel",
        # trap
        "get_top_selling_products_by_region",
        "get_customer_orders_summary",
        "get_revenue_forecast",
        "get_supplier_scorecard",
        "get_employee_directory",
        "get_campaign_summary",
        "get_ticket_summary",
        "get_budget_summary",
        "get_purchase_order_status",
        "get_module_rating_summary",
        "get_low_adoption_report",
        "get_customer_engagement_score",
        "get_quarterly_growth_rate",
        # lookup
        "get_order_by_customer_name",
        "get_ticket_by_email",
        "get_campaign_by_name",
        "get_supplier_by_company",
        "get_employee_by_name",
        "get_product_by_title",
        "get_department_by_label",
        "get_budget_by_department_name",
        "get_review_by_customer_and_product",
        "get_expense_by_description",
        # synthetic
        "get_ai_recommendation",
        "get_risk_score",
        "get_health_score",
        "predict_churn",
        "get_nps_score",
        "get_market_benchmark",
        "get_industry_average",
        "get_competitor_analysis",
        "get_sentiment_score",
        "get_anomaly_report",
        "get_data_quality_score",
        "get_audit_log",
        "get_system_status",
        "get_user_permissions",
        "get_api_usage",
    }
)
