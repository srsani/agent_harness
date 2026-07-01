from agent_harness.db.schema import get_connection, init_db
from agent_harness.tools import enterprise


def test_get_top_selling_products_uses_distinct_subscription_activations(tmp_path, monkeypatch):
    db_path = tmp_path / "enterprise.db"
    init_db(db_path)
    monkeypatch.setattr(enterprise, "get_connection", lambda: get_connection(db_path))

    with get_connection(db_path) as conn:
        conn.execute(
            "INSERT INTO categories(id, name, description) VALUES (1, 'Finance', 'Finance')"
        )
        conn.execute(
            """
            INSERT INTO products(id, category_id, name, description, annual_license_usd,
                                 active_deployments, created_at)
            VALUES
              (1, 1, 'Revenue Forecast Model', 'Forecasting', 100.0, 10, '2026-01-01'),
              (2, 1, 'Cash Flow Predictor', 'Cash flow', 200.0, 10, '2026-01-01')
            """
        )
        conn.execute(
            """
            INSERT INTO customers(id, email, full_name, city, country, tier, created_at)
            VALUES (1, 'analyst@example.com', 'A Analyst', 'Paris', 'FR', 'standard',
                    '2026-01-01T00:00:00')
            """
        )
        conn.execute(
            """
            INSERT INTO orders(id, customer_id, status, total_amount, created_at, shipped_at)
            VALUES
              (1, 1, 'delivered', 300.0, '2026-06-30T00:00:00', NULL),
              (2, 1, 'shipped', 100.0, '2026-06-29T00:00:00', NULL),
              (3, 1, 'cancelled', 900.0, '2026-06-28T00:00:00', NULL)
            """
        )
        conn.execute(
            """
            INSERT INTO order_items(id, order_id, product_id, seats, unit_price)
            VALUES
              (1, 1, 1, 3, 100.0),
              (2, 2, 1, 1, 100.0),
              (3, 3, 2, 9, 100.0)
            """
        )
        conn.commit()

    assert enterprise.get_top_selling_products(limit=5, days=90) == [
        {
            "module_name": "Revenue Forecast Model",
            "business_function": "Finance",
            "activation_count": 2,
            "subscription_revenue": 400.0,
        }
    ]
