"""Lab 3.2: connect, run queries with parameters, read rows as tuples or dicts."""

import psycopg
from psycopg.rows import dict_row

from settings import pg_dsn


def main() -> None:
    """Run the four query examples of step 3.2 against pg1."""
    # Connection address, read from PG_DSN in the .env file.
    dsn = pg_dsn()

    with psycopg.connect(dsn) as conn:
        print("server version:", conn.info.server_version)

        # 1. A simple query. Each row comes back as a Python tuple.
        with conn.cursor() as cur:
            cur.execute("SELECT count(*) FROM orders")
            row = cur.fetchone()
            # fetchone() returns None when no row is left; count(*) always returns one row.
            if row is None:
                raise RuntimeError("count(*) returned no row")
            order_count = row[0]
            print("orders:", order_count)

        # 2. A query with parameters. %s marks where a value goes.
        country = "VE"
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id, name FROM customers WHERE country = %s ORDER BY id LIMIT %s",
                (country, 3),
            )
            for row in cur.fetchall():
                print("tuple row:", row)

        # 3. Rows as dictionaries, with a named parameter.
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                "SELECT sku, price, attrs ->> 'category' AS category "
                "FROM products WHERE id = %(product_id)s",
                {"product_id": 7},
            )
            print("dict row:", cur.fetchone())

        # 4. An SQL injection attempt. The text is sent as a value, never as SQL.
        malicious_input = "VE' OR '1'='1"
        with conn.cursor() as cur:
            cur.execute("SELECT count(*) FROM customers WHERE country = %s", (malicious_input,))
            row = cur.fetchone()
            if row is None:
                raise RuntimeError("count(*) returned no row")
            print("rows matched by the injection attempt:", row[0])


if __name__ == "__main__":
    main()
