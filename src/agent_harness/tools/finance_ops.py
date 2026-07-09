"""Finance / Budgets tools — typed functions over the budgets / expenses tables.

Named `finance_ops` (not `finance`) to avoid clashing with the `Finance` business function
label used elsewhere in the schema (categories.name, departments.function).
"""

from __future__ import annotations

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


def list_budgets(year: int = 0) -> list[dict[str, Any]]:
    """Return all department budgets, optionally filtered to one year.

    Args:
        year: Four-digit budget year. 0 means no filter (all years).
    """
    if year:
        return _rows(
            """
            SELECT b.id, d.name AS department, b.year, b.category, b.allocated_usd
            FROM budgets b
            JOIN departments d ON d.id = b.department_id
            WHERE b.year = ?
            ORDER BY d.name, b.category
            """,
            year,
        )
    return _rows(
        """
        SELECT b.id, d.name AS department, b.year, b.category, b.allocated_usd
        FROM budgets b
        JOIN departments d ON d.id = b.department_id
        ORDER BY b.year DESC, d.name, b.category
        """
    )


def get_budget(budget_id: int) -> dict[str, Any] | None:
    """Get a single budget's allocation details.

    Args:
        budget_id: The budget's integer ID.
    """
    return _row(
        """
        SELECT b.id, d.name AS department, b.year, b.category, b.allocated_usd
        FROM budgets b
        JOIN departments d ON d.id = b.department_id
        WHERE b.id = ?
        """,
        budget_id,
    )


def search_expenses(
    department: str = "", category: str = "", min_amount: float = 0.0, limit: int = 20
) -> list[dict[str, Any]]:
    """Search expense line items by department, budget category, or minimum amount.

    Args:
        department: Partial department name match (case-insensitive). Empty = no filter.
        category: Exact budget category filter
            ('opex','capex','headcount','travel','marketing_spend').
        min_amount: Minimum amount_usd. 0 means no filter.
        limit: Maximum results (default 20).
    """
    conditions = ["1=1"]
    params: list[Any] = []
    if department:
        conditions.append("d.name LIKE ?")
        params.append(f"%{department}%")
    if category:
        conditions.append("e.category = ?")
        params.append(category)
    if min_amount > 0:
        conditions.append("e.amount_usd >= ?")
        params.append(min_amount)
    params.append(limit)
    where = " AND ".join(conditions)
    return _rows(
        f"""
        SELECT e.id, d.name AS department, e.category, e.amount_usd, e.incurred_at, e.description
        FROM expenses e
        JOIN departments d ON d.id = e.department_id
        WHERE {where}
        ORDER BY e.amount_usd DESC
        LIMIT ?
        """,
        *params,
    )


def get_expense(expense_id: int) -> dict[str, Any] | None:
    """Get a single expense line item's details.

    Args:
        expense_id: The expense's integer ID.
    """
    return _row(
        """
        SELECT e.id, d.name AS department, e.category, e.amount_usd, e.incurred_at, e.description
        FROM expenses e
        JOIN departments d ON d.id = e.department_id
        WHERE e.id = ?
        """,
        expense_id,
    )


def get_budget_variance(budget_id: int) -> dict[str, Any] | None:
    """Compute a budget's variance: allocated_usd minus actual expenses charged against it.
    Positive variance means under budget; negative means over budget.

    Args:
        budget_id: The budget's integer ID.
    """
    return _row(
        """
        SELECT b.id, d.name AS department, b.year, b.category, b.allocated_usd,
               ROUND(COALESCE(SUM(e.amount_usd), 0), 2) AS actual_spend_usd,
               ROUND(b.allocated_usd - COALESCE(SUM(e.amount_usd), 0), 2) AS variance_usd
        FROM budgets b
        JOIN departments d ON d.id = b.department_id
        LEFT JOIN expenses e ON e.budget_id = b.id
        WHERE b.id = ?
        GROUP BY b.id
        """,
        budget_id,
    )


def get_department_spend(department: str, start_date: str, end_date: str) -> dict[str, Any]:
    """Aggregate a department's actual expense spend between two ISO-8601 dates (inclusive).

    Args:
        department: Exact department name, e.g. 'R&D Engineering'.
        start_date: Start of the period, e.g. '2024-01-01'.
        end_date: End of the period, e.g. '2024-03-31'.
    """
    return _row(
        """
        SELECT d.name AS department,
               COUNT(e.id) AS expense_count,
               ROUND(SUM(e.amount_usd), 2) AS total_spend_usd
        FROM expenses e
        JOIN departments d ON d.id = e.department_id
        WHERE d.name = ? AND e.incurred_at BETWEEN ? AND ?
        GROUP BY d.name
        """,
        department,
        start_date,
        end_date + "T23:59:59",
    )


def get_capex_summary(year: int) -> list[dict[str, Any]]:
    """Return capital expenditure (capex category) allocated vs. actual spend by department
    for a given year.

    Args:
        year: Four-digit year, e.g. 2024.
    """
    return _rows(
        """
        SELECT d.name AS department, b.allocated_usd,
               ROUND(COALESCE(SUM(e.amount_usd), 0), 2) AS actual_spend_usd
        FROM budgets b
        JOIN departments d ON d.id = b.department_id
        LEFT JOIN expenses e ON e.budget_id = b.id
        WHERE b.category = 'capex' AND b.year = ?
        GROUP BY b.id
        ORDER BY b.allocated_usd DESC
        """,
        year,
    )


def get_expense_category_breakdown(start_date: str, end_date: str) -> list[dict[str, Any]]:
    """Return total expense spend by budget category between two ISO-8601 dates (inclusive).

    Args:
        start_date: Start of the period, e.g. '2024-01-01'.
        end_date: End of the period, e.g. '2024-03-31'.
    """
    return _rows(
        """
        SELECT category, COUNT(*) AS expense_count, ROUND(SUM(amount_usd), 2) AS total_spend_usd
        FROM expenses
        WHERE incurred_at BETWEEN ? AND ?
        GROUP BY category
        ORDER BY total_spend_usd DESC
        """,
        start_date,
        end_date + "T23:59:59",
    )


def get_forecast_vs_actual(department: str, year: int) -> list[dict[str, Any]]:
    """Return a department's allocated budget vs. actual spend, by category, for a given year.

    Args:
        department: Exact department name, e.g. 'Finance & Accounting'.
        year: Four-digit budget year.
    """
    return _rows(
        """
        SELECT b.category, b.allocated_usd,
               ROUND(COALESCE(SUM(e.amount_usd), 0), 2) AS actual_spend_usd,
               ROUND(b.allocated_usd - COALESCE(SUM(e.amount_usd), 0), 2) AS variance_usd
        FROM budgets b
        JOIN departments d ON d.id = b.department_id
        LEFT JOIN expenses e ON e.budget_id = b.id
        WHERE d.name = ? AND b.year = ?
        GROUP BY b.id
        ORDER BY b.category
        """,
        department,
        year,
    )
