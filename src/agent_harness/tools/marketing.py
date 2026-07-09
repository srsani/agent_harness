"""Marketing Campaign tools — typed functions over the campaigns / campaign_performance tables."""

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


def list_campaigns() -> list[dict[str, Any]]:
    """Return all marketing campaigns with channel, status, and budget."""
    return _rows(
        "SELECT id, name, channel, status, budget_usd, start_date, end_date "
        "FROM campaigns ORDER BY start_date DESC"
    )


def get_campaign(campaign_id: int) -> dict[str, Any] | None:
    """Get full details for one marketing campaign.

    Args:
        campaign_id: The campaign's integer ID.
    """
    return _row(
        "SELECT id, name, channel, status, budget_usd, start_date, end_date "
        "FROM campaigns WHERE id = ?",
        campaign_id,
    )


def search_campaigns(
    channel: str = "", status: str = "", min_budget: float = 0.0, limit: int = 20
) -> list[dict[str, Any]]:
    """Search campaigns by channel, status, or minimum budget.

    Args:
        channel: Exact channel filter ('email','paid_search','social','webinar','content','events').
        status: Exact status filter ('planned','active','completed','paused').
        min_budget: Minimum budget_usd. 0 means no filter.
        limit: Maximum results (default 20).
    """
    conditions = ["1=1"]
    params: list[Any] = []
    if channel:
        conditions.append("channel = ?")
        params.append(channel)
    if status:
        conditions.append("status = ?")
        params.append(status)
    if min_budget > 0:
        conditions.append("budget_usd >= ?")
        params.append(min_budget)
    params.append(limit)
    where = " AND ".join(conditions)
    return _rows(
        f"""
        SELECT id, name, channel, status, budget_usd, start_date, end_date
        FROM campaigns WHERE {where}
        ORDER BY budget_usd DESC LIMIT ?
        """,
        *params,
    )


def get_campaign_performance(campaign_id: int) -> dict[str, Any] | None:
    """Return a campaign's funnel totals: impressions, clicks, leads, conversions, spend.

    Args:
        campaign_id: The campaign's integer ID.
    """
    return _row(
        """
        SELECT c.id, c.name,
               SUM(cp.impressions) AS total_impressions,
               SUM(cp.clicks) AS total_clicks,
               SUM(cp.leads) AS total_leads,
               SUM(cp.conversions) AS total_conversions,
               ROUND(SUM(cp.spend_usd), 2) AS total_spend_usd
        FROM campaigns c
        JOIN campaign_performance cp ON cp.campaign_id = c.id
        WHERE c.id = ?
        GROUP BY c.id
        """,
        campaign_id,
    )


def get_campaign_roi(campaign_id: int) -> dict[str, Any] | None:
    """Compute a campaign's ROI using the average non-cancelled subscription value as the
    assumed value of each conversion: roi = (conversions * avg_subscription_value - spend) / spend.

    Args:
        campaign_id: The campaign's integer ID.
    """
    perf = get_campaign_performance(campaign_id)
    if perf is None or not perf.get("total_spend_usd"):
        return perf
    avg_value_row = _row(
        "SELECT AVG(total_amount) AS avg_value FROM orders WHERE status != 'cancelled'"
    )
    avg_value = avg_value_row["avg_value"] if avg_value_row else 0.0
    conversions = perf["total_conversions"] or 0
    spend = perf["total_spend_usd"]
    estimated_value = conversions * avg_value
    roi = (estimated_value - spend) / spend if spend else None
    return {
        **perf,
        "assumed_value_per_conversion": round(avg_value, 2),
        "estimated_value_usd": round(estimated_value, 2),
        "roi": round(roi, 4) if roi is not None else None,
    }


def get_top_campaigns_by_conversion(limit: int = 5) -> list[dict[str, Any]]:
    """Return the campaigns with the most total conversions across their run.

    Args:
        limit: How many campaigns to return (default 5).
    """
    return _rows(
        """
        SELECT c.id, c.name, c.channel,
               SUM(cp.conversions) AS total_conversions,
               ROUND(SUM(cp.spend_usd), 2) AS total_spend_usd
        FROM campaigns c
        JOIN campaign_performance cp ON cp.campaign_id = c.id
        GROUP BY c.id
        ORDER BY total_conversions DESC, c.name ASC
        LIMIT ?
        """,
        limit,
    )


def get_channel_spend_breakdown(days: int = 180) -> list[dict[str, Any]]:
    """Return total spend and conversions by marketing channel over the last N days.

    Args:
        days: Look-back window in days (default 180).
    """
    return _rows(
        """
        WITH latest AS (
          SELECT MAX(month || '-01') AS max_month FROM campaign_performance
        )
        SELECT c.channel,
               ROUND(SUM(cp.spend_usd), 2) AS total_spend_usd,
               SUM(cp.conversions) AS total_conversions
        FROM campaign_performance cp
        JOIN campaigns c ON c.id = cp.campaign_id
        CROSS JOIN latest
        WHERE date(cp.month || '-01') >= date(latest.max_month, ? || ' days')
        GROUP BY c.channel
        ORDER BY total_spend_usd DESC
        """,
        f"-{days}",
    )


def get_lead_conversion_funnel(campaign_id: int) -> dict[str, Any] | None:
    """Return a campaign's full funnel with conversion rates at each stage.

    Args:
        campaign_id: The campaign's integer ID.
    """
    perf = get_campaign_performance(campaign_id)
    if perf is None:
        return None
    impressions = perf["total_impressions"] or 0
    clicks = perf["total_clicks"] or 0
    leads = perf["total_leads"] or 0
    conversions = perf["total_conversions"] or 0
    return {
        **perf,
        "click_through_rate_pct": round(100 * clicks / impressions, 3) if impressions else None,
        "lead_rate_pct": round(100 * leads / clicks, 3) if clicks else None,
        "conversion_rate_pct": round(100 * conversions / leads, 3) if leads else None,
    }


def get_monthly_marketing_spend(year: int) -> list[dict[str, Any]]:
    """Return total marketing spend and conversions across all campaigns, by month, for a year.

    Args:
        year: Four-digit year, e.g. 2024.
    """
    return _rows(
        """
        SELECT month, ROUND(SUM(spend_usd), 2) AS total_spend_usd, SUM(conversions) AS total_conversions
        FROM campaign_performance
        WHERE month LIKE ? || '-%'
        GROUP BY month
        ORDER BY month
        """,
        str(year),
    )
