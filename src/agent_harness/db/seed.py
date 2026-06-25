"""Seed the e-commerce database with realistic simulated data."""

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
    ("Electronics",   "Gadgets, devices, and accessories"),
    ("Books",         "Fiction, non-fiction, and technical titles"),
    ("Home & Garden", "Furniture, decor, and outdoor gear"),
    ("Clothing",      "Apparel for all ages and occasions"),
    ("Sports",        "Equipment and gear for active lifestyles"),
]

PRODUCTS: dict[str, list[tuple[str, str, float, int]]] = {
    "Electronics": [
        ("Wireless Noise-Cancelling Headphones", "Over-ear Bluetooth 5.3 with 30 h battery",  249.99, 120),
        ("Mechanical Keyboard 75%",              "Hot-swap RGB with PBT keycaps",              129.99,  85),
        ("4K Webcam",                            "2160p/30fps with built-in ring light",        89.99,  60),
        ("USB-C Hub 10-in-1",                    "Docking station with 4K HDMI and 100W PD",    49.99, 200),
        ("Smart Watch Gen 4",                    "AMOLED, GPS, blood oxygen sensor",           299.99,  40),
        ("Portable SSD 1TB",                     "USB 3.2 Gen2, 1050 MB/s read",               99.99, 175),
        ("Gaming Mouse",                         "16000 DPI optical sensor, 7 buttons",         59.99, 150),
        ("27-inch Monitor",                      "IPS, 165Hz, 1ms, G-Sync compatible",         399.99,  25),
        ("Bluetooth Speaker",                    "360° sound, IP67 waterproof, 24 h battery",   79.99,  90),
        ("Laptop Stand Adjustable",              "Aluminium, foldable, supports up to 20 kg",   39.99, 300),
    ],
    "Books": [
        ("Clean Code",                   "R. Martin — timeless software craftsmanship",    34.99, 500),
        ("Designing Data-Intensive Apps", "M. Kleppmann — distributed systems bible",      49.99, 350),
        ("The Pragmatic Programmer",     "Hunt & Thomas — 20th anniversary edition",       39.99, 280),
        ("Python Cookbook",              "Beazley & Jones — recipes for modern Python",    44.99, 210),
        ("Atomic Habits",                "J. Clear — tiny changes, remarkable results",    16.99, 600),
        ("Deep Work",                    "Cal Newport — rules for focused success",        15.99, 450),
        ("The Go Programming Language",  "Donovan & Kernighan — authoritative Go guide",  44.99, 190),
        ("Staff Engineer",               "W. Larson — leadership beyond the management",   29.99, 160),
        ("Thinking, Fast and Slow",      "Daniel Kahneman — two-system theory of mind",   17.99, 520),
        ("Zero to One",                  "Peter Thiel — notes on startups and the future",14.99, 400),
    ],
    "Home & Garden": [
        ("Standing Desk 140cm",       "Electric height-adjustable, memory presets",       499.99,  15),
        ("Ergonomic Office Chair",    "Lumbar support, 4D armrests, mesh back",           349.99,  20),
        ("Air Purifier HEPA H13",     "360° intake, 5-stage filtration, whisper-quiet",   179.99,  55),
        ("Grow Light Full Spectrum",  "Samsung LM301H LEDs, dimmable timer",              89.99,  80),
        ("French Press 1L",           "Double-wall stainless, stays hot 4 h",             29.99, 220),
        ("Cast Iron Skillet 10in",    "Pre-seasoned, oven-safe to 500°F",                 44.99, 300),
        ("Robot Vacuum Gen 3",        "LiDAR mapping, self-emptying base",               399.99,  18),
        ("Bamboo Cutting Board Set",  "3-piece, juice groove, dishwasher-safe",           24.99, 400),
        ("Indoor Herb Garden Kit",    "Self-watering planter, LED grow light, seeds",     54.99, 130),
        ("Smart Thermostat",          "Learns your schedule, works with Alexa & Google", 149.99,  45),
    ],
    "Clothing": [
        ("Merino Wool Base Layer",   "Odour-resistant, moisture-wicking, 190 gsm",  79.99, 200),
        ("Slim-Fit Chinos",          "Stretch cotton, 5-pocket, 12 colours",         59.99, 350),
        ("Waterproof Rain Jacket",   "20k/20k Gore-Tex, packable, pit-zip vents",   149.99, 110),
        ("Running Shoes GT-2200",    "Gel cushioning, AHAR+ outsole, wide fit",     129.99, 180),
        ("Crew-Neck Sweatshirt",     "300 gsm French terry, pre-washed, unisex",     44.99, 500),
        ("Wool Beanie",              "100% Shetland wool, ribbed, one size",          19.99, 600),
        ("Compression Socks 3-pack", "Graduated 15-20 mmHg, OTC medical grade",      29.99, 450),
        ("Leather Belt 35mm",        "Full-grain vegetable-tanned, nickel buckle",    49.99, 250),
        ("Linen Shirt Long Sleeve",  "120s linen, mother-of-pearl buttons, relaxed",  69.99, 175),
        ("Packable Down Vest",       "800-fill power, 20D ripstop, weighs 180 g",    89.99, 140),
    ],
    "Sports": [
        ("Yoga Mat 6mm",              "Non-slip natural rubber, alignment lines",       49.99, 320),
        ("Adjustable Dumbbell Set",   "5-50 lb selector, compact footprint",           399.99,  22),
        ("Pull-Up Bar Doorframe",     "No-screws, 100 kg capacity, foam grips",         34.99, 280),
        ("Resistance Bands 5-pack",  "11–60 lb latex loop bands, door anchor kit",     24.99, 450),
        ("Foam Roller Deep Tissue",   "High-density EVA, textured surface, 33cm",       19.99, 500),
        ("Hydration Backpack 15L",    "2 L bladder, chest/hip straps, rain cover",      79.99, 100),
        ("Cycling Computer GPS",      "Colour touchscreen, ANT+/BLE, 40 h battery",   249.99,  35),
        ("Jump Rope Speed",           "Ball-bearing handles, 3m adjustable cable",      14.99, 600),
        ("Kettlebell 16kg",           "Cast iron, powder-coated, flat base",            59.99, 150),
        ("Swimming Goggles Anti-Fog", "UV400, mirrored lens, tri-fold case",            22.99, 380),
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
    "Absolutely love it!", "Exceeded expectations", "Great quality",
    "Would buy again", "Highly recommended", "Brilliant product",
    "Five stars — no hesitation", "Impressed by the build quality",
]
REVIEW_TITLES_MID = [
    "Decent for the price", "Does the job", "Good but not perfect",
    "Solid enough", "Worth the money", "Meets expectations",
]
REVIEW_TITLES_BAD = [
    "Disappointed", "Not as described", "Had issues from day one",
    "Returned after a week", "Expected better quality",
]
REVIEW_BODIES = {
    5: [
        "This is exactly what I needed. Build quality is excellent and it arrived quickly.",
        "Superb. I've been using it daily for weeks and it still feels brand new.",
        "Perfect product. My whole team has ordered one now.",
    ],
    4: [
        "Really solid. Minor gripe with the packaging but the product itself is great.",
        "Works very well. Setup was easy and performance is impressive.",
        "Good value. A couple of small improvements would make it perfect.",
    ],
    3: [
        "It's fine. Does what it says, nothing more. Shipping was slow.",
        "Average product. Not bad, but I've seen better at this price point.",
        "Decent but could be better. Customer service was helpful when I had a question.",
    ],
    2: [
        "Doesn't quite live up to the marketing. Had to contact support twice.",
        "Below average. A few features don't work as described.",
    ],
    1: [
        "Stopped working after two weeks. Returning it.",
        "Very disappointing. Nothing like the photos online.",
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
    product_prices: dict[int, float] = {}
    for cat_name, items in PRODUCTS.items():
        cat_id = cat_ids[cat_name]
        for pname, pdesc, price, stock in items:
            cur = conn.execute(
                "INSERT OR IGNORE INTO products(category_id,name,description,price,stock_quantity,created_at)"
                " VALUES (?,?,?,?,?,?)",
                (cat_id, pname, pdesc, price, stock, _random_dt(three_years_ago, now - timedelta(days=365))),
            )
            if cur.lastrowid:
                pid = cur.lastrowid
            else:
                row = conn.execute("SELECT id FROM products WHERE name=?", (pname,)).fetchone()
                pid = row[0]
            product_ids.append(pid)
            product_prices[pid] = price

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
            qty = RNG.randint(1, 3)
            price = product_prices[pid]
            total += qty * price
            line_items.append((pid, qty, price))

        cur = conn.execute(
            "INSERT INTO orders(customer_id,status,total_amount,created_at,shipped_at)"
            " VALUES (?,?,?,?,?)",
            (customer_id, status, round(total, 2), created, shipped_at),
        )
        oid = cur.lastrowid
        order_ids.append(oid)
        for pid, qty, price in line_items:
            conn.execute(
                "INSERT INTO order_items(order_id,product_id,quantity,unit_price)"
                " VALUES (?,?,?,?)",
                (oid, pid, qty, price),
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
