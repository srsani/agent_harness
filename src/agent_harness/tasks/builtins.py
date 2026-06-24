"""Shared tasks for comparing harnesses and architectures.

Tasks are grouped:
  - Generic (no database required)
  - E-commerce (require the seeded SQLite database)
"""

TASKS: dict[str, str] = {
    # ── generic ───────────────────────────────────────────────────────────────
    "hello": (
        "Reply in one short sentence: what is 17 + 25? "
        "Do not use any tools."
    ),
    "reasoning": (
        "A bat and a ball cost $1.10 in total. The bat costs $1.00 more than the ball. "
        "How much does the ball cost? Show your reasoning, then give the final answer."
    ),
    "hn-research": (
        "Across the top Hacker News feed, find the highest-scored story with at least "
        "50 points. Summarize its title, score, and the main theme in 2-3 sentences."
    ),

    # ── e-commerce: single-tool lookups ───────────────────────────────────────
    "ec-top-products": (
        "What are the top 5 best-selling products by units sold in the last 90 days? "
        "List each product's name, category, units sold, and revenue."
    ),
    "ec-low-stock": (
        "Which products are running low on stock (25 or fewer units)? "
        "List their names, categories, and current stock quantities."
    ),
    "ec-customer-lookup": (
        "Look up customer with ID 42. Show their full profile, total lifetime spend, "
        "and their last 5 orders with status and total amount."
    ),

    # ── e-commerce: multi-step / join reasoning ───────────────────────────────
    "ec-category-analysis": (
        "For each product category, calculate: total revenue in the last 6 months, "
        "number of unique customers who bought from that category, and the single "
        "best-selling product by revenue. Present the results sorted by revenue descending."
    ),
    "ec-gold-customers": (
        "Find all gold-tier customers. For each one, show their name, city, "
        "lifetime value, and their single highest-value order (order ID + amount). "
        "Which city has the most gold customers?"
    ),
    "ec-review-insights": (
        "Which 3 products have the highest average rating (with at least 5 reviews)? "
        "And which 3 products have the lowest average rating (with at least 3 reviews)? "
        "For each, show the product name, average rating, and a sample review title."
    ),
    "ec-monthly-trend": (
        "Show monthly revenue and order count for the last calendar year available in the "
        "database. In which month was revenue highest? What was the month-over-month "
        "growth from the lowest to the highest month?"
    ),

    # ── e-commerce: complex analytical ────────────────────────────────────────
    "ec-churn-risk": (
        "Identify customers who placed at least 2 orders but have NOT placed any order "
        "in the last 180 days. List up to 10 such customers with their name, tier, "
        "last order date, and total lifetime value, sorted by lifetime value descending."
    ),
    "ec-basket-size": (
        "What is the average number of items per order and average order value, "
        "broken down by customer tier (standard, silver, gold)? "
        "Which tier has the highest average basket size?"
    ),
}
