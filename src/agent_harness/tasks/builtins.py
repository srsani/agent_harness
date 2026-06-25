"""Shared tasks for comparing harnesses and architectures.

Tasks are grouped:
  - Generic (no database required)
  - Enterprise Decision Intelligence (require the seeded SQLite database)
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

    # ── enterprise Decision Intelligence: single-tool lookups ─────────────────
    "adi-top-modules": (
        "What are the top 5 most-activated analytics modules in the last 90 days? "
        "List each module's name, business function, activation count, and subscription revenue."
    ),
    "adi-low-adoption": (
        "Which analytics modules have 25 or fewer active deployments (low adoption alert)? "
        "List their names, business functions, and current deployment counts."
    ),
    "adi-user-lookup": (
        "Look up business user with ID 42. Show their full profile, total lifetime spend, "
        "and their last 5 subscriptions with status and total value."
    ),

    # ── enterprise Decision Intelligence: multi-step / join reasoning ─────────
    "adi-function-analysis": (
        "For each business function, calculate: total subscription revenue in the last 6 months, "
        "number of unique users who subscribed to at least one module from that function, and the "
        "single highest-revenue module. Present the results sorted by revenue descending."
    ),
    "adi-executive-users": (
        "Find all gold-tier users. For each one, show their name, city, "
        "lifetime subscription value, and their single highest-value subscription (ID + amount). "
        "Which city has the most gold-tier users?"
    ),
    "adi-module-ratings": (
        "Which 3 analytics modules have the highest average user rating (with at least 5 ratings)? "
        "And which 3 modules have the lowest average rating (with at least 3 ratings)? "
        "For each, show the module name, average rating, and a sample review title."
    ),
    "adi-monthly-trend": (
        "Show monthly subscription revenue and activation count for the last calendar year in the "
        "database. In which month was revenue highest? What was the month-over-month "
        "growth from the lowest to the highest month?"
    ),

    # ── enterprise Decision Intelligence: complex analytical ──────────────────
    "adi-disengagement-risk": (
        "Identify users who activated at least 2 subscriptions but have had NO new subscription "
        "in the last 180 days. List up to 10 such users with their name, engagement tier, "
        "last subscription date, and total lifetime value, sorted by lifetime value descending."
    ),
    "adi-portfolio-depth": (
        "What is the average number of modules per subscription and average subscription value, "
        "broken down by engagement tier (standard, silver, gold)? "
        "Which tier has the deepest average analytics portfolio?"
    ),
}
