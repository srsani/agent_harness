"""Shared tasks for comparing harnesses and architectures.

Tasks are grouped:
  - Generic (no database required)
  - Enterprise Decision Intelligence (require the seeded SQLite database)
"""

TASKS: dict[str, str] = {
    # ── generic ───────────────────────────────────────────────────────────────
    "hello": ("Reply in one short sentence: what is 17 + 25? Do not use any tools."),
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
    "adi-function-opportunity": (
        "For each business function, calculate total subscription revenue in the last 6 months, "
        "unique users in the last 6 months, highest-revenue module, average module rating across "
        "reviewed modules, and number of low-adoption modules with 25 or fewer active deployments. "
        "Return only the top 3 business functions by revenue, sorted by revenue descending, with "
        "columns: business_function, revenue_6m, unique_users_6m, highest_revenue_module, "
        "avg_module_rating, low_adoption_modules."
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
    # ═══════════════════════════════════════════════════════════════════════════
    # Architecture routing benchmark
    #
    # Six task groups below are each designed so that ONE of the six enterprise
    # architectures has a structural advantage answering it. See
    # `agent_harness.tasks.routing_benchmark` for the paired "why this
    # architecture wins here" explanations, rejected alternatives, observable
    # routing signals, and architecture-pair decision-boundary rules.
    # ═══════════════════════════════════════════════════════════════════════════
    # ── enterprise-react: atomic single/low-call typed-tool lookups ───────────
    # One (occasionally two) typed tool calls fully answer the question. No
    # fan-out to batch and no ambiguous/novel query shape to justify raw SQL —
    # ReAct's one-call-per-turn loop finishes in a single round trip, and
    # CodeMode's sandbox spin-up buys nothing when there is nothing to batch.
    "react-customer-profile-77": (
        "Look up business user with ID 77. Show their full name, city, tier, "
        "and lifetime subscription value."
    ),
    "react-product-detail-15": (
        "Get full details for analytics module ID 15, including its business "
        "function, annual license cost, and average user rating."
    ),
    "react-low-adoption-threshold-20": (
        "Which analytics modules have 20 or fewer active deployments? "
        "List their names and current deployment counts."
    ),
    "react-top-modules-30days": (
        "What are the top 5 most-activated analytics modules in the last 30 days? "
        "List each module's name and activation count."
    ),
    "react-recent-reviews-module-8": (
        "Show the 5 most recent user satisfaction ratings for analytics module ID 8, "
        "including rating, title, and reviewer name."
    ),
    "react-sales-summary-60d": (
        "Summarize subscription activity for the most recent 60 days of data: "
        "total subscriptions, unique users, and total revenue."
    ),
    "react-category-catalogue": (
        "List every business function category along with its description."
    ),
    "react-search-products-supplychain": (
        "Find analytics modules in the Supply Chain business function with an "
        "annual license cost of $9,000 or less. List their names and annual license costs."
    ),
    "react-search-customers-gold-london": (
        "Find all gold-tier business users based in London. List their names and email addresses."
    ),
    "react-customer-orders-history-130": (
        "Show the subscription history for business user ID 130: list each "
        "subscription's status, total amount, and creation date, most recent first."
    ),
    "react-order-detail-500": (
        "Get full subscription details for order ID 500, including status, "
        "total amount, and every analytics module line item with seats and unit price."
    ),
    "react-customer-lifetime-value-17": (
        "What is the total lifetime spend and top business function for business "
        "user ID 17, based on their delivered subscriptions only?"
    ),
    # ── enterprise-codemode: typed-tool fan-out over many entities ────────────
    # Answering correctly means calling a typed tool once per entity (10-25+
    # items) and combining the results client-side. A ReAct agent needs one
    # model round trip per call; CodeMode loops over the same typed tools
    # inside a single sandboxed script.
    "codemode-gold-lifetime-scan": (
        "For every gold-tier business user, compute lifetime subscription value "
        "(sum of non-cancelled subscription totals) and the date of their most "
        "recent subscription. Return the 10 with the highest lifetime value: "
        "name, city, lifetime value, and most recent subscription date."
    ),
    "codemode-customer-batch-lookup": (
        "Look up business users with IDs 3, 17, 24, 38, 45, 52, 61, 74, 88, 93, "
        "101, 115, 122, 136, 149, 158, 163, 171, 184, 197. For each, report their "
        "tier and lifetime subscription value. Return only the gold-tier ones, "
        "sorted by lifetime value descending."
    ),
    "codemode-module-review-gap-scan": (
        "Check analytics modules with IDs 2, 5, 9, 12, 18, 22, 27, 31, 34, 39, "
        "43, 47, 52, 56, 61, 65, 70, 74, 79, 83, 88, 92, 97, 100 for user "
        "satisfaction ratings. List the ones that currently have zero ratings, "
        "along with their business function and active deployment count."
    ),
    "codemode-order-batch-audit": (
        "Look up subscriptions (orders) with IDs 5, 40, 85, 120, 200, 260, 310, "
        "375, 430, 500, 560, 610, 670, 740, 800, 860, 920, 980, 1040, 1100. "
        "Compute the combined total_amount of only the ones with status "
        "'delivered', and list every distinct analytics module name that "
        "appears across all 20 subscriptions."
    ),
    "codemode-top-module-review-quality": (
        "Find the top 10 most-activated analytics modules in the last 90 days. "
        "For each, compute the percentage of their user satisfaction ratings "
        "that are 4 or 5 stars. Return all 10 ranked by that percentage "
        "descending, with module name, activation count, and the 4-5 star percentage."
    ),
    "codemode-gold-churn-scan": (
        "Among all gold-tier business users, identify every one who has had no "
        "subscription of any status in the last 120 days. List their name, "
        "city, and the date of their most recent subscription (or 'never "
        "subscribed' if they have none)."
    ),
    "codemode-lowstock-unreviewed": (
        "Find every analytics module with 25 or fewer active deployments. For "
        "each, check whether it has any user satisfaction ratings, and list the "
        "ones with zero ratings along with business function and deployment count."
    ),
    "codemode-category-price-spread": (
        "For each of the 5 business functions, find the minimum, maximum, and "
        "average annual license cost among its analytics modules. Return one "
        "row per business function."
    ),
    "codemode-recent-multi-subscribers": (
        "Look up business users with IDs 150 through 170. For each, find how "
        "many subscriptions (of any status) they placed in the last 90 days and "
        "their total spend on those. List only the ones with 2 or more recent "
        "subscriptions."
    ),
    "codemode-bundle-scan": (
        "Look up subscriptions (orders) with IDs 10, 55, 100, 150, 210, 260, "
        "320, 370, 430, 480, 540, 590, 650, 700, 760, 810, 870, 920, 980, 1030. "
        "Identify which ones include 3 or more distinct analytics modules, and "
        "for each, list the customer name, order status, and included module names."
    ),
    "codemode-most-reviewed-deepdive": (
        "Find the 10 analytics modules with the most user satisfaction ratings "
        "overall. For each, report the average rating and the title of its "
        "single most recent review. Sort all 10 by review count descending."
    ),
    "codemode-early-cohort-value": (
        "Among business users who created their account within the first 90 "
        "days of the earliest account creation date in the system, compute "
        "each one's lifetime subscription value. Return the 10 with the "
        "highest lifetime value, including name and account creation date."
    ),
    # ── enterprise-mcp-react: low-call lookups over the FastMCP tool server ───
    # Same shape as the enterprise-react group (1-3 calls, no fan-out) so
    # correctness is identical either way — the routing signal here is
    # deployment context (tools centrally hosted/shared behind a standard
    # protocol, per-call auditability) rather than a different right answer.
    "mcpreact-customer-profile-155": (
        "Look up business user with ID 155. Show their profile: full name, "
        "email, city, tier, and lifetime subscription value."
    ),
    "mcpreact-product-detail-40": (
        "Get full details for analytics module ID 40, including annual "
        "license cost, active deployments, and average rating."
    ),
    "mcpreact-low-adoption-threshold-15": (
        "Which analytics modules have 15 or fewer active deployments? "
        "List their names and deployment counts."
    ),
    "mcpreact-top-modules-45days": (
        "What are the top 5 most-activated analytics modules in the last 45 "
        "days? List module name and activation count."
    ),
    "mcpreact-recent-reviews-module-60": (
        "Show the 3 most recent user satisfaction ratings for analytics "
        "module ID 60, including rating and title."
    ),
    "mcpreact-sales-summary-30d": (
        "Summarize subscription activity for the most recent 30 days of "
        "data: total subscriptions, unique users, and total revenue."
    ),
    "mcpreact-search-products-finance": (
        "Find analytics modules in the Finance business function priced at "
        "$8,000 or less. List their names and annual license costs."
    ),
    "mcpreact-search-customers-silver-berlin": (
        "Find all silver-tier business users based in Berlin. List their names and email addresses."
    ),
    "mcpreact-customer-orders-history-180": (
        "Show the subscription history for business user ID 180: status, "
        "total amount, and creation date, most recent first."
    ),
    "mcpreact-order-detail-900": (
        "Get full subscription details for order ID 900, including status, "
        "total amount, and every analytics module line item."
    ),
    "mcpreact-customer-lifetime-value-110": (
        "What is the total lifetime spend and top business function for "
        "business user ID 110, based on delivered subscriptions only?"
    ),
    "mcpreact-revenue-by-month-lastyear": (
        "Show monthly subscription revenue and subscription counts for the "
        "last calendar year in the database."
    ),
    # ── enterprise-mcp-codemode: FastMCP tool fan-out, batched in one sandbox ─
    # Same fan-out mechanics as the enterprise-codemode group, but against the
    # FastMCP-served tool set — the ideal fit when the tool layer is centrally
    # hosted/shared (e.g. across multiple bots or non-Python clients) yet the
    # workload still needs CodeMode's batching to stay fast over many calls.
    "mcpcodemode-silver-lifetime-scan": (
        "For every silver-tier business user, compute lifetime subscription "
        "value and total number of non-cancelled subscriptions. Return the 10 "
        "with the highest lifetime value: name, city, lifetime value, and "
        "subscription count."
    ),
    "mcpcodemode-customer-batch-lookup": (
        "Look up business users with IDs 6, 19, 28, 33, 47, 55, 66, 71, 84, 96, "
        "108, 119, 127, 141, 152, 160, 169, 176, 188, 199. For each, report "
        "tier and lifetime subscription value. Return only the silver-tier "
        "ones, sorted by lifetime value descending."
    ),
    "mcpcodemode-module-review-gap-scan-rd": (
        "Check every analytics module in the Research & Development business "
        "function for user satisfaction ratings. List the ones with zero "
        "ratings along with their active deployment count."
    ),
    "mcpcodemode-order-batch-audit": (
        "Look up subscriptions (orders) with IDs 15, 60, 95, 140, 190, 250, "
        "300, 355, 410, 470, 520, 580, 630, 690, 750, 820, 880, 940, 1000, "
        "1060, 1120, 1180. Compute the combined total_amount of only the ones "
        "with status 'shipped', and list every distinct business function "
        "represented across all subscriptions."
    ),
    "mcpcodemode-top-module-price-value": (
        "Find the top 10 most-activated analytics modules in the last 60 "
        "days. For each, compute its revenue per active deployment "
        "(subscription_revenue / active_deployments). Return all 10 ranked "
        "by that ratio descending, with module name, activation count, and "
        "the ratio."
    ),
    "mcpcodemode-silver-churn-scan": (
        "Among all silver-tier business users, identify every one who has "
        "had no subscription of any status in the last 150 days. List their "
        "name, city, and the date of their most recent subscription (or "
        "'never subscribed' if they have none)."
    ),
    "mcpcodemode-highprice-lowrating-scan": (
        "Find every analytics module with an annual license cost of $12,000 "
        "or more. For each, report its average user satisfaction rating, and "
        "list the ones with an average rating below 3.5 (or no ratings at all)."
    ),
    "mcpcodemode-category-deployment-spread": (
        "For each of the 5 business functions, find the minimum, maximum, "
        "and average active_deployments among its analytics modules. Return "
        "one row per business function."
    ),
    "mcpcodemode-recent-multi-subscribers": (
        "Look up business users with IDs 1 through 40. For each, find how "
        "many subscriptions (of any status) they placed in the last 60 days "
        "and their total spend on those. List only the ones with 2 or more "
        "recent subscriptions."
    ),
    "mcpcodemode-bundle-scan": (
        "Look up subscriptions (orders) with IDs 20, 65, 110, 160, 220, 270, "
        "330, 380, 440, 490, 550, 600, 660, 710, 770, 820, 890, 930, 990, "
        "1040. Identify which ones include 4 or more distinct analytics "
        "modules, and for each, list the customer name, order status, and "
        "included module names."
    ),
    "mcpcodemode-least-reviewed-deepdive": (
        "Find the 10 analytics modules with the fewest user satisfaction "
        "ratings among modules that have at least 1 rating. For each, report "
        "the average rating and the title of its earliest review. Sort all "
        "10 by review count ascending."
    ),
    "mcpcodemode-recent-cohort-value": (
        "Among business users who created their account within the most "
        "recent 90 days before the latest account creation date in the "
        "system, compute each one's lifetime subscription value. Return the "
        "10 with the highest lifetime value, including name and account "
        "creation date."
    ),
    # ── enterprise-sql-react: ad-hoc analysis no typed tool covers ────────────
    # Every question below needs a custom join/filter shape (self-joins,
    # multi-attribute cohorts, integrity checks) that doesn't map onto any of
    # the 13 semantic tools. A single hand-written SELECT answers it in one
    # call; the smaller 3-tool surface also means no risk of the model
    # reaching for a misleadingly-named semantic tool instead of writing SQL.
    "sqlreact-module-affinity": (
        "Which pair of analytics modules is most frequently subscribed "
        "together within the same subscription (order)? Report the two "
        "module names and how many subscriptions include both."
    ),
    "sqlreact-median-price": (
        "What is the median annual license cost across all analytics modules "
        "currently in the catalogue?"
    ),
    "sqlreact-revenue-per-module-efficiency": (
        "Which business function has the highest subscription revenue per "
        "analytics module it offers (total non-cancelled subscription "
        "revenue divided by number of modules in that function)? Report the "
        "business function and the ratio."
    ),
    "sqlreact-cross-functional-power-users": (
        "Which business users have a non-cancelled subscription to modules "
        "from at least 4 different business functions? List their names and "
        "how many distinct business functions they've subscribed to."
    ),
    "sqlreact-bundle-percentage": (
        "What percentage of non-cancelled subscriptions include more than 2 "
        "distinct analytics modules?"
    ),
    "sqlreact-tier-rating-gap": (
        "Which analytics modules have an average rating from gold-tier "
        "reviewers that differs by more than 1.0 star from their average "
        "rating from standard-tier reviewers (among modules with at least 1 "
        "rating from each tier)? List the module name and both averages."
    ),
    "sqlreact-fast-movers": (
        "Which business users placed their first subscription within 7 days "
        "of creating their account? List their names and the number of days "
        "between account creation and their first subscription."
    ),
    "sqlreact-mom-active-users": (
        "For each of the last 6 calendar months of data, what is the "
        "month-over-month percentage change in the number of unique business "
        "users who placed a non-cancelled subscription?"
    ),
    "sqlreact-data-integrity-check": (
        "Are there any subscriptions where the recorded total_amount doesn't "
        "match the sum of (seats x unit_price) across their line items? List "
        "any mismatches with the order ID, recorded total, and computed total."
    ),
    "sqlreact-city-subscription-value": (
        "Which 3 cities have the highest average non-cancelled subscription "
        "value per business user based there?"
    ),
    "sqlreact-early-cohort-comparison": (
        "Business users who created their account within the earliest 90 "
        "days of the dataset: what is their combined lifetime subscription "
        "value, compared to the combined lifetime subscription value of "
        "everyone else?"
    ),
    "sqlreact-rating-trend": (
        "For analytics modules with at least 6 ratings, compare the average "
        "rating of their most recent half of reviews (by date) to their "
        "earliest half. List modules where the recent half's average rating "
        "is at least 0.5 stars higher than the earlier half's, along with "
        "both averages."
    ),
    # ── enterprise-sql-codemode: multi-query analysis + custom computation ────
    # Each question needs several dependent SQL queries and/or statistics that
    # SQL can't express directly (correlation, standard deviation, Jaccard
    # similarity) — fetch-then-compute inside one sandboxed script beats both
    # a single hand-rolled mega-query (sql-react) and typed tools that have no
    # equivalent bulk-statistics endpoint at all.
    "sqlcodemode-rating-distribution-top5": (
        "Find the 5 analytics modules with the most user satisfaction "
        "ratings. For each, report how many ratings it has at each star "
        "level (1 through 5)."
    ),
    "sqlcodemode-price-rating-correlation": (
        "Compute the Pearson correlation coefficient between an analytics "
        "module's annual license cost and its average user rating, across "
        "all modules with at least 3 ratings. Report the coefficient rounded "
        "to 3 decimal places."
    ),
    "sqlcodemode-subscription-outliers": (
        "Compute the mean and standard deviation of total_amount across all "
        "delivered subscriptions. List every delivered subscription whose "
        "total_amount is more than 2 standard deviations above the mean, "
        "with its order ID, customer name, and total_amount."
    ),
    "sqlcodemode-customer-spend-jump": (
        "Across all business users, find the single largest month-over-month "
        "increase in subscription spend between two consecutive calendar "
        "months in which they had at least one non-cancelled subscription. "
        "Report the customer name, the two months, and the size of the increase."
    ),
    "sqlcodemode-price-consistency-by-function": (
        "For each business function, compute the coefficient of variation "
        "(standard deviation divided by mean) of its analytics modules' "
        "annual license costs. Report the business function with the lowest "
        "coefficient of variation (most consistent pricing) and its value."
    ),
    "sqlcodemode-subscription-cadence": (
        "Among business users with at least 3 non-cancelled subscriptions, "
        "compute each one's average number of days between consecutive "
        "subscriptions. Report the 3 users with the fastest (lowest) average "
        "cadence, including their name and average days."
    ),
    "sqlcodemode-weighted-quality-score": (
        "Using the exact formula weighted_score = avg_rating * ln(active_deployments + 1), "
        "compute a weighted score for every analytics module with at least 1 "
        "rating. Report the top 3 modules platform-wide by this score, with "
        "their avg_rating, active_deployments, and weighted_score rounded to "
        "3 decimal places."
    ),
    "sqlcodemode-unreviewed-below-median": (
        "Find analytics modules that have zero user satisfaction ratings AND "
        "have active_deployments below the platform-wide median "
        "active_deployments value. List their names, business functions, and "
        "active_deployments."
    ),
    "sqlcodemode-gold-category-overlap": (
        "Among the 5 gold-tier business users with the highest lifetime "
        "subscription value, find the pair whose sets of business functions "
        "(from their non-cancelled subscriptions) have the highest Jaccard "
        "similarity (size of intersection divided by size of union). Report "
        "both customer names and the similarity value rounded to 3 decimal places."
    ),
    "sqlcodemode-seat-normalization-simulation": (
        "For the last 6 calendar months of data, recompute what monthly "
        "subscription revenue would have been if every line item had exactly "
        "2 seats instead of its actual seat count (using the same per-seat "
        "unit_price), and compare it to the actual monthly revenue for "
        "non-cancelled subscriptions. Report both series by month."
    ),
    "sqlcodemode-revenue-momentum": (
        "For each business function, compute its subscription revenue in the "
        "most recent calendar month of data versus its average monthly "
        "revenue over the trailing 12 months. Report the business function "
        "with the highest ratio of most-recent-month revenue to "
        "trailing-12-month average, along with the ratio."
    ),
    "sqlcodemode-composite-engagement-score": (
        "Using the exact formula engagement_score = (lifetime_subscription_value / 1000) "
        "+ (number_of_reviews_written * 50) + (100 if the user's most recent "
        "non-cancelled subscription is within the last 90 days else 0), "
        "compute this score for every gold-tier business user. Report the "
        "top 5 by score, including each component value."
    ),
    # ── minimal: no database or tool access needed at all ─────────────────────
    # Every question below is fully self-contained — all inputs are given in
    # the prompt text itself, and the answer is pure arithmetic/text/logic
    # reasoning. None of it touches customers, products, orders, or any other
    # entity in the enterprise database. A plain agent with zero tools and zero
    # harness capabilities answers these in a single model turn; every one of
    # the six enterprise architectures pays for tool-selection reasoning (and,
    # for CodeMode/MCP variants, sandbox spin-up or transport setup) for tools
    # that are structurally guaranteed to go unused.
    "minimal-percentage-discount": (
        "A subscription is priced at $1,200 per year. If a 15% early-renewal "
        "discount is applied, what is the discounted price? Round to two "
        "decimal places."
    ),
    "minimal-compound-interest": (
        "If $5,000 is invested at an annual interest rate of 6%, compounded "
        "monthly, what is the balance after 2 years? Round to two decimal "
        "places."
    ),
    "minimal-list-statistics": (
        "Given the dataset [12, 45, 7, 23, 56, 34, 19, 8], calculate the mean, "
        "median, and sample standard deviation. Round each to two decimal "
        "places."
    ),
    "minimal-string-reversal-vowels": (
        "Reverse the string 'DecisionIntelligence' and count how many vowels "
        "(a, e, i, o, u, case-insensitive) it contains."
    ),
    "minimal-date-formatting": (
        "Convert the date 2026-11-03 (YYYY-MM-DD) into the format "
        "'Month D, YYYY' (e.g., 'January 5, 2026')."
    ),
    "minimal-fizzbuzz-range": (
        "For the numbers 1 through 100, list every number that is divisible by both 3 and 5."
    ),
    "minimal-caesar-cipher": (
        "Encode the word 'AGENT' using a Caesar cipher with a shift of 3 "
        "(A becomes D, B becomes E, etc., wrapping Z back to C)."
    ),
    "minimal-palindrome-check": (
        "Is the phrase 'A man a plan a canal Panama' a palindrome when "
        "ignoring spaces, punctuation, and case? Answer yes or no, and show "
        "the cleaned string used for the check."
    ),
    "minimal-gcd-lcm": (
        "What are the greatest common divisor and least common multiple of 48 and 180?"
    ),
    "minimal-word-count-unique": (
        "Count the total number of words and the number of unique words "
        "(case-insensitive) in the sentence: 'The quick brown fox jumps over "
        "the lazy dog and the fox runs away'."
    ),
    "minimal-unit-conversion": (
        "Convert 82 kilometers per hour to miles per hour, using 1 km = "
        "0.621371 miles. Round to two decimal places."
    ),
    "minimal-marble-probability": (
        "A bag contains 5 red, 3 blue, and 2 green marbles. If one marble is "
        "drawn at random, what is the probability it is NOT blue? Express "
        "the answer as a reduced fraction and as a percentage rounded to one "
        "decimal place."
    ),
    # ── minimal: conversational small talk / FAQ, no lookup possible or needed ─
    # These are pure chit-chat/meta questions with no factual claim to verify —
    # there is no customer, product, or order to look up, and no computation to
    # perform. Ground truth is intentionally non-deterministic (see
    # "conversational" type in generate_ground_truth.py): the pass condition is
    # a brief, on-topic conversational reply, not a specific string or number.
    # Any of the six enterprise architectures would either burn a turn
    # reasoning about which (nonexistent) tool applies, or worse, attempt to
    # query the database for something that was never asked.
    "minimal-greeting-howareyou": ("Hi there! How are you doing today?"),
    "minimal-greeting-whatsup": ("Hey, what's up?"),
    "minimal-faq-capabilities": ("Hello! What kinds of things can you help me with?"),
}
