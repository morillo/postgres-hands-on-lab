"""The Lab 3 scripts print what docs/03-python.md says they print."""

from pathlib import Path

import psycopg
import pytest

from conftest import run_script


@pytest.mark.usefixtures("seeded_database")
def test_basics_parameters_and_injection(tmp_path: Path) -> None:
    """01_basics.py reads the seed and the injection payload matches 0 rows."""
    lines = run_script("01_basics.py", tmp_path)
    assert lines[0].startswith("server version: 17")
    assert lines[1:] == [
        "orders: 200000",
        "tuple row: (2, 'Customer 2')",
        "tuple row: (10, 'Customer 10')",
        "tuple row: (18, 'Customer 18')",
        "dict row: {'sku': 'SKU-0007', 'price': Decimal('264.99'), 'category': 'tools'}",
        "rows matched by the injection attempt: 0",
    ]


@pytest.mark.usefixtures("seeded_database")
def test_transactions_restore_the_price(tmp_path: Path) -> None:
    """02_transactions.py prints the documented states and puts SKU-0005 back at 190.99."""
    lines = run_script("02_transactions.py", tmp_path)
    assert lines == [
        "default autocommit: False",
        "status after a SELECT: INTRANS",
        "status after a SELECT: IDLE",
        "start price: 190.99",
        "status inside block: INTRANS",
        "after committed block: 191.99",
        "rolled back because: products_price_check",
        "after failed block: 191.99",
        "inner savepoint rolled back; outer block continues",
        "after savepoint demo: 192.99",
        "restored price: 190.99",
    ]


@pytest.mark.usefixtures("seeded_database")
def test_bulk_load_stream_and_export(tmp_path: Path) -> None:
    """03_bulk.py loads 50,000 rows, streams 2,000 new orders and writes 1,197 CSV rows."""
    lines = run_script("03_bulk.py", tmp_path)
    assert "rows loaded: 50000" in lines
    assert "new orders counted by streaming: 2000" in lines
    assert "wrote data/paid_orders_2025_03.csv with 1197 data rows" in lines

    csv_lines = (tmp_path / "data" / "paid_orders_2025_03.csv").read_text().splitlines()
    assert csv_lines[:3] == [
        "id,customer_id,ordered_at",
        "32503,1258,2025-03-01 01:29:31+00",
        "32504,9177,2025-03-01 01:32:08+00",
    ]


def test_orm_runs_twice_and_cleans_up(seeded_database: str, tmp_path: Path) -> None:
    """04_orm.py prints the documented revenue and leaves no rows behind, so it can re-run."""
    expected_revenue = [
        "BR 28552912.35",
        "CA 34564410.01",
        "DE 28101181.70",
        "ES 39019327.97",
        "JP 19824567.64",
        "MX 17974721.72",
        "US 33280965.60",
        "VE 32562370.33",
    ]
    for _run in range(2):
        lines = run_script("04_orm.py", tmp_path)
        assert lines[0] == "SQL that will be sent:"
        revenue_start = lines.index("BR 28552912.35")
        assert lines[revenue_start : revenue_start + 8] == expected_revenue
        assert "Customer 42 has 20 orders" in lines
        assert "first order has 1 item(s); first product: SKU-0074" in lines
        assert lines[-1] == "cleaned up"

    with psycopg.connect(seeded_database) as conn:
        row = conn.execute(
            "SELECT count(*) FROM customers WHERE email = 'orm@example.com'"
        ).fetchone()
    assert row == (0,)
