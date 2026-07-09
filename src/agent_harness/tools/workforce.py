"""Workforce / HR tools — typed functions over departments / employees / performance_reviews."""

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


def list_departments() -> list[dict[str, Any]]:
    """Return all internal departments with their business function and annual budget."""
    return _rows("SELECT id, name, function, budget_usd FROM departments ORDER BY name")


def get_department(department_id: int) -> dict[str, Any] | None:
    """Get a single department's details including current headcount.

    Args:
        department_id: The department's integer ID.
    """
    return _row(
        """
        SELECT d.id, d.name, d.function, d.budget_usd,
               COUNT(e.id) AS headcount
        FROM departments d
        LEFT JOIN employees e ON e.department_id = d.id AND e.is_active = 1
        WHERE d.id = ?
        GROUP BY d.id
        """,
        department_id,
    )


def get_employee(employee_id: int) -> dict[str, Any] | None:
    """Get a single employee's profile, including department and manager name.

    Args:
        employee_id: The employee's integer ID.
    """
    return _row(
        """
        SELECT e.id, e.full_name, e.title, d.name AS department, e.hired_at,
               e.salary_usd, m.full_name AS manager_name, e.is_active, e.departed_at
        FROM employees e
        JOIN departments d ON d.id = e.department_id
        LEFT JOIN employees m ON m.id = e.manager_id
        WHERE e.id = ?
        """,
        employee_id,
    )


def search_employees(
    department: str = "", title: str = "", min_tenure_years: float = 0.0, limit: int = 20
) -> list[dict[str, Any]]:
    """Search active employees by department name, job title, or minimum tenure.

    Args:
        department: Partial department name match (case-insensitive). Empty = no filter.
        title: Partial job title match (case-insensitive). Empty = no filter.
        min_tenure_years: Minimum years since hired_at. 0 means no filter.
        limit: Maximum results (default 20).
    """
    conditions = ["e.is_active = 1"]
    params: list[Any] = []
    if department:
        conditions.append("d.name LIKE ?")
        params.append(f"%{department}%")
    if title:
        conditions.append("e.title LIKE ?")
        params.append(f"%{title}%")
    if min_tenure_years > 0:
        conditions.append("(JULIANDAY('now') - JULIANDAY(e.hired_at)) / 365.25 >= ?")
        params.append(min_tenure_years)
    params.append(limit)
    where = " AND ".join(conditions)
    return _rows(
        f"""
        SELECT e.id, e.full_name, e.title, d.name AS department, e.hired_at
        FROM employees e
        JOIN departments d ON d.id = e.department_id
        WHERE {where}
        ORDER BY e.full_name
        LIMIT ?
        """,
        *params,
    )


def get_department_headcount(department_id: int) -> dict[str, Any] | None:
    """Return a department's active headcount and average salary.

    Args:
        department_id: The department's integer ID.
    """
    return _row(
        """
        SELECT d.id, d.name,
               COUNT(e.id) AS active_headcount,
               ROUND(AVG(e.salary_usd), 2) AS avg_salary_usd
        FROM departments d
        LEFT JOIN employees e ON e.department_id = d.id AND e.is_active = 1
        WHERE d.id = ?
        GROUP BY d.id
        """,
        department_id,
    )


def get_attrition_rate(department_id: int, days: int = 365) -> dict[str, Any] | None:
    """Compute a department's attrition rate: employees who departed in the last N days
    divided by the department's average headcount in that window.

    Args:
        department_id: The department's integer ID.
        days: Look-back window in days (default 365).
    """
    return _row(
        """
        SELECT d.id, d.name,
               COUNT(e.id) AS total_ever_employed,
               SUM(CASE WHEN e.is_active = 0 AND e.departed_at >= datetime('now', ? || ' days')
                        THEN 1 ELSE 0 END) AS departed_count,
               ROUND(100.0 * SUM(CASE WHEN e.is_active = 0
                     AND e.departed_at >= datetime('now', ? || ' days') THEN 1 ELSE 0 END)
                     / COUNT(e.id), 2) AS attrition_rate_pct
        FROM departments d
        LEFT JOIN employees e ON e.department_id = d.id
        WHERE d.id = ?
        GROUP BY d.id
        """,
        f"-{days}",
        f"-{days}",
        department_id,
    )


def get_performance_review_summary(employee_id: int) -> dict[str, Any] | None:
    """Return an employee's performance review history and average rating.

    Args:
        employee_id: The employee's integer ID.
    """
    return _row(
        """
        SELECT e.id, e.full_name,
               COUNT(r.id) AS review_count,
               ROUND(AVG(r.rating), 2) AS avg_rating,
               MAX(r.review_date) AS most_recent_review_date
        FROM employees e
        LEFT JOIN performance_reviews r ON r.employee_id = e.id
        WHERE e.id = ?
        GROUP BY e.id
        """,
        employee_id,
    )


def get_compensation_band(title: str) -> dict[str, Any] | None:
    """Return the min, max, and average current salary for a given job title.

    Args:
        title: Exact job title, e.g. 'Senior Manager'.
    """
    return _row(
        """
        SELECT ? AS title,
               COUNT(*) AS employee_count,
               MIN(salary_usd) AS min_salary_usd,
               MAX(salary_usd) AS max_salary_usd,
               ROUND(AVG(salary_usd), 2) AS avg_salary_usd
        FROM employees
        WHERE title = ? AND is_active = 1
        """,
        title,
        title,
    )


def get_open_positions() -> list[dict[str, Any]]:
    """Return departments with recent attrition (departed in the last 90 days) that haven't
    had a same-title backfill hired since, as a proxy for open positions."""
    return _rows(
        """
        SELECT d.name AS department, e.title, e.full_name AS departed_employee, e.departed_at
        FROM employees e
        JOIN departments d ON d.id = e.department_id
        WHERE e.is_active = 0
          AND e.departed_at >= datetime('now', '-90 days')
          AND NOT EXISTS (
              SELECT 1 FROM employees e2
              WHERE e2.department_id = e.department_id
                AND e2.title = e.title
                AND e2.is_active = 1
                AND e2.hired_at > e.departed_at
          )
        ORDER BY e.departed_at DESC
        """
    )
