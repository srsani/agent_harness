"""Seed the enterprise Decision Intelligence benchmark database with realistic simulated data."""

from __future__ import annotations

import random
import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path

from agent_harness.db.schema import get_connection, init_db

# ── deterministic seed for reproducible data ──────────────────────────────────
RNG = random.Random(42)

# ── reference data ────────────────────────────────────────────────────────────

CATEGORIES = [
    ("Finance",               "Financial planning, forecasting, and capital allocation analytics"),
    ("Supply Chain",          "Inventory, logistics, demand forecasting, and procurement intelligence"),
    ("Sales & Marketing",     "Revenue performance, pipeline analytics, and go-to-market optimisation"),
    ("Research & Development","Portfolio prioritisation, trial analytics, and time-to-market tracking"),
    ("HR & People",           "Workforce planning, talent retention, and performance management analytics"),
]

# (name, description, annual_license_usd, active_deployments)
PRODUCTS: dict[str, list[tuple[str, str, float, int]]] = {
    "Finance": [
        ("Revenue Forecast Model",       "AI-driven quarterly and annual revenue prediction with scenario analysis",      12000.0,  87),
        ("Budget Variance Dashboard",    "Real-time spend vs. plan tracking with drill-down by cost centre",               8500.0, 120),
        ("Cash Flow Predictor",          "13-week rolling cash flow forecast with liquidity risk signals",                  9500.0,  64),
        ("P&L Scenario Simulator",       "Multi-variable what-if modelling for profit and loss projections",              11000.0,  45),
        ("Working Capital Optimizer",    "Inventory-to-cash cycle analysis with optimisation recommendations",              7500.0,  38),
        ("CapEx ROI Tracker",            "Capital investment return modelling with payback period analysis",                6500.0,  55),
        ("Cost Allocation Engine",       "Activity-based cost distribution across departments and products",                8000.0,  72),
        ("FX Exposure Monitor",          "Currency risk dashboard with hedging strategy recommendations",                   5500.0,  29),
        ("Earnings Risk Analyzer",       "Volatility and downside scenario analysis for quarterly earnings",                9000.0,  33),
        ("Shareholder Value Scorecard",  "Long-term value creation KPIs aligned with investor expectations",              10500.0,  18),
    ],
    "Supply Chain": [
        ("Demand Forecast Engine",          "ML-powered demand prediction at SKU level with seasonal adjustment",         14000.0,  95),
        ("Inventory Optimization Suite",    "Min/max stock level recommendations with carrying cost analysis",            11500.0,  78),
        ("Supplier Performance Tracker",    "On-time delivery, quality scores, and risk ratings by supplier",              7000.0, 110),
        ("Logistics Cost Analyzer",         "Freight spend breakdown with lane-level optimisation opportunities",           8500.0,  65),
        ("Lead Time Predictor",             "Predictive supply lead times with disruption early-warning signals",           9500.0,  52),
        ("Stockout Risk Monitor",           "Probabilistic out-of-stock alerts 30–60 days ahead of occurrence",            6500.0,  88),
        ("Warehouse Utilisation Dashboard", "Capacity utilisation, pick efficiency, and slotting optimisation",             7500.0,  43),
        ("Transportation Network Optimizer","Carrier mix and routing recommendations to reduce freight cost",              12500.0,  31),
        ("Order Fulfilment Tracker",        "End-to-end order status with SLA breach prediction",                          5500.0, 140),
        ("Procurement Savings Analyzer",    "Contract compliance, maverick spend, and negotiation opportunity finder",    10000.0,  57),
    ],
    "Sales & Marketing": [
        ("Revenue Performance Dashboard",   "Real-time revenue vs. target with team and regional drill-down",             10000.0, 130),
        ("Sales Pipeline Analyzer",         "Pipeline coverage, stage conversion rates, and deal risk scoring",            9000.0,  98),
        ("Campaign ROI Optimizer",          "Marketing spend attribution with channel mix optimisation",                   8500.0,  75),
        ("Customer Acquisition Cost Tracker","CAC by channel, segment, and cohort with payback period modelling",          7000.0,  60),
        ("Market Share Monitor",            "Competitive position tracking using external market signals",                 11000.0,  42),
        ("Channel Mix Optimizer",           "AI-recommended budget allocation across digital and physical channels",        9500.0,  55),
        ("Price Elasticity Model",          "Demand sensitivity analysis enabling data-driven pricing decisions",          12000.0,  37),
        ("Quota Attainment Tracker",        "Individual and team quota progress with attainment probability forecast",      6000.0, 115),
        ("GTM Readiness Planner",           "Go-to-market readiness scoring for new products and market entries",          8000.0,  28),
        ("Territory Performance Analyzer",  "Geographic revenue analysis with whitespace opportunity identification",       7500.0,  49),
    ],
    "Research & Development": [
        ("Clinical Trial Optimizer",         "Trial site selection, patient recruitment, and timeline risk modelling",    18000.0,  22),
        ("Portfolio Prioritisation Engine",  "R&D investment scoring by expected value, risk, and strategic fit",         15000.0,  35),
        ("Time-to-Market Predictor",         "Development stage gating with launch timeline probability distributions",   13000.0,  41),
        ("R&D Spend Analyzer",               "Cost-per-programme tracking with benchmark comparisons",                     9000.0,  58),
        ("Innovation Pipeline Dashboard",    "Active project status, resource allocation, and milestone tracking",         8000.0,  67),
        ("Trial Success Probability Model",  "Bayesian phase transition probability with historical calibration",          16000.0,  19),
        ("Regulatory Timeline Tracker",      "Submission-to-approval cycle modelling with bottleneck identification",     12000.0,  30),
        ("IP Portfolio Analyzer",            "Patent strength, expiry risk, and competitive exposure scoring",            10000.0,  25),
        ("Resource Allocation Optimizer",    "Cross-portfolio scientist and lab capacity planning recommendations",        11000.0,  44),
        ("Competitive Intelligence Monitor", "Competitor pipeline tracking and differentiation analysis",                  7500.0,  72),
    ],
    "HR & People": [
        ("Workforce Planning Dashboard",    "Headcount forecasting by function with attrition and hiring scenarios",       9500.0,  80),
        ("Talent Retention Predictor",      "Flight-risk scoring with personalised intervention recommendations",          11000.0,  65),
        ("Diversity & Inclusion Scorecard", "Representation metrics, pay equity analysis, and gap closure tracking",       7000.0,  90),
        ("Performance Management Analyzer", "Rating distribution analysis, calibration support, and bias detection",       8500.0,  55),
        ("Compensation Benchmarking Tool",  "Market pay positioning with range penetration and equity risk alerts",         9000.0,  48),
        ("Employee Engagement Monitor",     "Pulse survey analytics with drivers of engagement and churn signals",          6500.0, 105),
        ("Succession Planning Engine",      "Critical role coverage, bench strength scoring, and readiness timelines",    10000.0,  38),
        ("Hiring Funnel Optimizer",         "Recruitment pipeline conversion rates with source quality analysis",           7500.0,  72),
        ("Training ROI Analyzer",           "Learning investment returns linked to performance and retention outcomes",      5500.0,  88),
        ("Absenteeism Risk Tracker",        "Absence pattern analysis with productivity impact and early warning flags",    6000.0,  61),
    ],
}

FIRST_NAMES = [
    "Alice","Bob","Carol","David","Emma","Frank","Grace","Hank",
    "Iris","Jack","Karen","Liam","Mia","Noah","Olivia","Pete",
    "Quinn","Rosa","Sam","Tara","Uma","Vince","Wendy","Xander",
    "Yara","Zach","Ava","Ben","Claire","Dan","Elena","Felix",
    "Gina","Hugo","Ivy","Jake","Kim","Leo","Maya","Nate",
]
LAST_NAMES = [
    "Smith","Jones","Williams","Brown","Taylor","Davies","Evans","Wilson",
    "Thomas","Roberts","Johnson","Walker","Wright","Robinson","Thompson","White",
    "Hughes","Edwards","Green","Hall","Lewis","Harris","Clarke","Patel",
    "Turner","Martin","Anderson","Jackson","Garcia","Martinez","Moore","Nguyen",
]
CITIES = [
    ("New York","US"),("Los Angeles","US"),("Chicago","US"),("Austin","US"),
    ("London","GB"),("Manchester","GB"),("Edinburgh","GB"),("Bristol","GB"),
    ("Berlin","DE"),("Hamburg","DE"),("Munich","DE"),
    ("Paris","FR"),("Lyon","FR"),
    ("Toronto","CA"),("Vancouver","CA"),
    ("Sydney","AU"),("Melbourne","AU"),
]
TIERS = ["standard", "standard", "standard", "silver", "silver", "gold"]

REVIEW_TITLES_GOOD = [
    "Transformed our decision-making", "Cut our analysis time by 80%",
    "Exactly the insights we needed", "Exceeded our accuracy targets",
    "Finally, data-driven forecasting", "Impressive predictive power",
    "Saved weeks of manual work", "Our leadership team relies on this daily",
]
REVIEW_TITLES_MID = [
    "Good starting point", "Useful but needs calibration",
    "Solid analytics, some data gaps", "Meets our core needs",
    "Promising, room to improve", "Covers most of our use cases",
]
REVIEW_TITLES_BAD = [
    "Data freshness issues", "Model needs more training data",
    "Results don't match our expectations", "Too many false positives",
    "Needs better integration with our data sources",
]
REVIEW_BODIES = {
    5: [
        "This module immediately surfaced insights we'd been missing for quarters. ROI was clear within the first month.",
        "The predictive accuracy is remarkable. We've integrated it into our weekly leadership reviews.",
        "Exactly what we needed to move from gut-feel to data-driven decisions. Our whole team uses it daily.",
    ],
    4: [
        "Very strong analytics with actionable recommendations. Minor gap in historical data depth but otherwise excellent.",
        "Works well for our use case. Onboarding was smooth and the insights are genuinely useful.",
        "Good value. A few more customisation options would make it perfect for our workflow.",
    ],
    3: [
        "It covers the basics well. We'd love deeper drill-down capability and faster data refresh.",
        "Adequate for standard reporting. Advanced scenarios still require SQL workarounds.",
        "Decent output. The customer success team was helpful when we needed guidance on interpretation.",
    ],
    2: [
        "The model's baseline assumptions don't align well with our industry. Required significant reconfiguration.",
        "Below our expectations. Several key metrics we rely on are missing from the current version.",
    ],
    1: [
        "Persistent data latency issues made this unusable for real-time decision-making.",
        "Very disappointing. The predictions were consistently off and support response was slow.",
    ],
}

ORDER_STATUSES = ["pending", "shipped", "delivered", "delivered", "delivered", "cancelled"]


# ── helpers ───────────────────────────────────────────────────────────────────

def _random_dt(start: datetime, end: datetime) -> str:
    delta = (end - start).total_seconds()
    return (start + timedelta(seconds=RNG.random() * delta)).isoformat(timespec="seconds")


def _email(first: str, last: str, n: int) -> str:
    domains = ["gmail.com", "yahoo.com", "outlook.com", "proton.me", "fastmail.com"]
    return f"{first.lower()}.{last.lower()}{n}@{RNG.choice(domains)}"


# ── seed ──────────────────────────────────────────────────────────────────────

def seed(conn: sqlite3.Connection, *, n_customers: int = 200, n_orders: int = 600) -> None:
    now = datetime.now(UTC).replace(tzinfo=None)
    three_years_ago = now - timedelta(days=3 * 365)

    # --- categories ---
    cat_ids: dict[str, int] = {}
    for name, desc in CATEGORIES:
        cur = conn.execute(
            "INSERT OR IGNORE INTO categories(name, description) VALUES (?,?)", (name, desc)
        )
        if cur.lastrowid:
            cat_ids[name] = cur.lastrowid
        else:
            row = conn.execute("SELECT id FROM categories WHERE name=?", (name,)).fetchone()
            cat_ids[name] = row[0]

    # --- products ---
    product_ids: list[int] = []
    product_prices: dict[int, float] = {}  # product_id → annual_license_usd
    for cat_name, items in PRODUCTS.items():
        cat_id = cat_ids[cat_name]
        for pname, pdesc, price, stock in items:
            cur = conn.execute(
                "INSERT OR IGNORE INTO products"
                "(category_id,name,description,annual_license_usd,active_deployments,created_at)"
                " VALUES (?,?,?,?,?,?)",
                (cat_id, pname, pdesc, price, stock, _random_dt(three_years_ago, now - timedelta(days=365))),
            )
            if cur.lastrowid:
                pid = cur.lastrowid
            else:
                row = conn.execute("SELECT id FROM products WHERE name=?", (pname,)).fetchone()
                pid = row[0]
            product_ids.append(pid)
            product_prices[pid] = price  # annual_license_usd per seat

    # --- customers ---
    customer_ids: list[int] = []
    used_emails: set[str] = set()
    for i in range(n_customers):
        first = RNG.choice(FIRST_NAMES)
        last = RNG.choice(LAST_NAMES)
        email = _email(first, last, i)
        while email in used_emails:
            email = _email(first, last, i + RNG.randint(100, 999))
        used_emails.add(email)
        city, country = RNG.choice(CITIES)
        tier = RNG.choice(TIERS)
        created = _random_dt(three_years_ago, now - timedelta(days=30))
        cur = conn.execute(
            "INSERT OR IGNORE INTO customers(email,full_name,city,country,tier,created_at)"
            " VALUES (?,?,?,?,?,?)",
            (email, f"{first} {last}", city, country, tier, created),
        )
        if cur.lastrowid:
            customer_ids.append(cur.lastrowid)
        else:
            # Already exists — fetch existing
            row = conn.execute("SELECT id FROM customers WHERE email=?", (email,)).fetchone()
            customer_ids.append(row[0])

    if not customer_ids:
        customer_ids = [
            row[0] for row in conn.execute("SELECT id FROM customers").fetchall()
        ]

    # --- orders + order_items ---
    one_year_ago = now - timedelta(days=365)
    order_ids: list[int] = []
    for _ in range(n_orders):
        customer_id = RNG.choice(customer_ids)
        status = RNG.choice(ORDER_STATUSES)
        created = _random_dt(one_year_ago, now)
        shipped_at = None
        if status in ("shipped", "delivered"):
            shipped_at = _random_dt(
                datetime.fromisoformat(created) + timedelta(days=1),
                datetime.fromisoformat(created) + timedelta(days=5),
            )

        # pick 1-4 distinct products
        n_items = RNG.randint(1, 4)
        chosen = RNG.sample(product_ids, k=min(n_items, len(product_ids)))
        total = 0.0
        line_items = []
        for pid in chosen:
            seats = RNG.randint(1, 3)
            price = product_prices[pid]
            total += seats * price
            line_items.append((pid, seats, price))

        cur = conn.execute(
            "INSERT INTO orders(customer_id,status,total_amount,created_at,shipped_at)"
            " VALUES (?,?,?,?,?)",
            (customer_id, status, round(total, 2), created, shipped_at),
        )
        oid = cur.lastrowid
        order_ids.append(oid)
        for pid, seats, price in line_items:
            conn.execute(
                "INSERT INTO order_items(order_id,product_id,seats,unit_price)"
                " VALUES (?,?,?,?)",
                (oid, pid, seats, price),
            )

    # --- reviews (≈25% of order-items, for delivered orders only) ---
    delivered_items = conn.execute(
        """
        SELECT oi.product_id, o.customer_id, o.created_at
        FROM order_items oi
        JOIN orders o ON o.id = oi.order_id
        WHERE o.status = 'delivered'
        """
    ).fetchall()

    seen: set[tuple[int, int]] = set()
    for row in delivered_items:
        if RNG.random() > 0.25:
            continue
        pid, cid, order_date = row[0], row[1], row[2]
        if (pid, cid) in seen:
            continue
        seen.add((pid, cid))

        rating = RNG.choices([1, 2, 3, 4, 5], weights=[2, 5, 15, 35, 43])[0]
        if rating >= 4:
            title = RNG.choice(REVIEW_TITLES_GOOD)
        elif rating == 3:
            title = RNG.choice(REVIEW_TITLES_MID)
        else:
            title = RNG.choice(REVIEW_TITLES_BAD)
        body = RNG.choice(REVIEW_BODIES[rating])
        review_date = _random_dt(
            datetime.fromisoformat(order_date) + timedelta(days=5),
            datetime.fromisoformat(order_date) + timedelta(days=60),
        )
        conn.execute(
            "INSERT OR IGNORE INTO reviews(product_id,customer_id,rating,title,body,created_at)"
            " VALUES (?,?,?,?,?,?)",
            (pid, cid, rating, title, body, review_date),
        )

    conn.commit()


def seed_db(path: Path | None = None) -> None:
    init_db(path)
    with get_connection(path) as conn:
        seed(conn)
