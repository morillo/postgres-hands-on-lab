"""The seed data matches the numbers the docs quote (step 1.8)."""

import psycopg


def test_seed_row_counts(seeded_database: str) -> None:
    """The seed loads 200 products, 10,000 customers, 200,000 orders, 400,001 lines."""
    with psycopg.connect(seeded_database) as conn:
        row = conn.execute(
            "SELECT (SELECT count(*) FROM products), (SELECT count(*) FROM customers), "
            "(SELECT count(*) FROM orders), (SELECT count(*) FROM order_items)"
        ).fetchone()
    assert row == (200, 10_000, 200_000, 400_001)


def test_order_status_skew(seeded_database: str) -> None:
    """Statuses split 180,000 / 14,000 / 4,000 / 2,000, the skew Lab 6 relies on."""
    with psycopg.connect(seeded_database) as conn:
        rows = conn.execute(
            "SELECT status, count(*) FROM orders GROUP BY status ORDER BY status"
        ).fetchall()
    assert dict(rows) == {"cancelled": 4_000, "new": 2_000, "paid": 14_000, "shipped": 180_000}


def test_every_customer_has_twenty_orders(seeded_database: str) -> None:
    """7919 is coprime with 10,000, so each customer gets exactly 20 orders."""
    with psycopg.connect(seeded_database) as conn:
        row = conn.execute(
            "SELECT min(order_count), max(order_count) FROM "
            "(SELECT count(*) AS order_count FROM orders GROUP BY customer_id) AS per_customer"
        ).fetchone()
    assert row == (20, 20)
