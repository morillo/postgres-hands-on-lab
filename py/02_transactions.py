"""Lab 3.3: how psycopg 3 handles transactions."""

from decimal import Decimal

import psycopg
from psycopg.rows import TupleRow

from settings import pg_dsn


def get_price(conn: psycopg.Connection[TupleRow], sku: str) -> Decimal:
    """Return the current price of one product.

    Args:
        conn: An open connection to pg1.
        sku: The product's SKU, for example "SKU-0005".

    Returns:
        The price, as an exact Decimal.

    Raises:
        LookupError: If no product has this SKU.
    """
    row = conn.execute("SELECT price FROM products WHERE sku = %s", (sku,)).fetchone()
    if row is None:
        raise LookupError(f"no product with SKU {sku}")
    return row[0]


def main() -> None:
    """Show the default mode, then autocommit with explicit transaction blocks."""
    dsn = pg_dsn()

    # 1. Default mode: the first statement silently opens a transaction.
    with psycopg.connect(dsn) as conn:
        print("default autocommit:", conn.autocommit)
        get_price(conn, "SKU-0005")
        print("status after a SELECT:", conn.info.transaction_status.name)

    # 2. Recommended mode: autocommit=True plus explicit transaction blocks.
    with psycopg.connect(dsn, autocommit=True) as conn:
        get_price(conn, "SKU-0005")
        print("status after a SELECT:", conn.info.transaction_status.name)
        print("start price:", get_price(conn, "SKU-0005"))

        # A. A transaction block commits when it ends normally.
        with conn.transaction():
            conn.execute("UPDATE products SET price = price + 1 WHERE sku = %s", ("SKU-0005",))
            print("status inside block:", conn.info.transaction_status.name)
        print("after committed block:", get_price(conn, "SKU-0005"))

        # B. An exception inside the block rolls the whole block back.
        try:
            with conn.transaction():
                conn.execute(
                    "UPDATE products SET price = price + 100 WHERE sku = %s", ("SKU-0005",)
                )
                conn.execute("UPDATE products SET price = -1 WHERE sku = %s", ("SKU-0005",))
        except psycopg.errors.CheckViolation as error:
            print("rolled back because:", error.diag.constraint_name)
        print("after failed block:", get_price(conn, "SKU-0005"))

        # C. A block inside a block is a savepoint: only the inner part is undone.
        with conn.transaction():
            conn.execute("UPDATE products SET price = price + 1 WHERE sku = %s", ("SKU-0005",))
            try:
                with conn.transaction():
                    conn.execute("INSERT INTO orders (customer_id) VALUES (%s)", (999999,))
            except psycopg.errors.ForeignKeyViolation:
                print("inner savepoint rolled back; outer block continues")
        print("after savepoint demo:", get_price(conn, "SKU-0005"))

        # Put the price back so the lab stays repeatable.
        with conn.transaction():
            conn.execute("UPDATE products SET price = price - 2 WHERE sku = %s", ("SKU-0005",))
        print("restored price:", get_price(conn, "SKU-0005"))


if __name__ == "__main__":
    main()
