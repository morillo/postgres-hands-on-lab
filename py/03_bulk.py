"""Lab 3.4: bulk load with COPY, stream a big result, export to CSV."""

import time
from pathlib import Path

import psycopg

from settings import pg_dsn

ROW_COUNT = 50_000


def main() -> None:
    """Compare executemany with COPY, stream with a server-side cursor, export a CSV."""
    dsn = pg_dsn()

    rows: list[tuple[int, str, int]] = []
    for i in range(ROW_COUNT):
        rows.append((i, f"event-{i}", i % 7))

    with psycopg.connect(dsn, autocommit=True) as conn:
        conn.execute("DROP TABLE IF EXISTS events")
        conn.execute("CREATE TABLE events (id int PRIMARY KEY, label text, bucket int)")

        # 1. executemany: one INSERT statement per row.
        start = time.perf_counter()
        with (
            conn.transaction(),
            conn.cursor() as cur,
        ):
            cur.executemany("INSERT INTO events (id, label, bucket) VALUES (%s, %s, %s)", rows)
        executemany_seconds = time.perf_counter() - start
        conn.execute("TRUNCATE events")

        # 2. COPY: one statement, all rows streamed in a compact format.
        start = time.perf_counter()
        with (
            conn.transaction(),
            conn.cursor() as cur,
            cur.copy("COPY events (id, label, bucket) FROM STDIN") as copy,
        ):
            for row in rows:
                copy.write_row(row)
        copy_seconds = time.perf_counter() - start

        count_row = conn.execute("SELECT count(*) FROM events").fetchone()
        if count_row is None:
            raise RuntimeError("count(*) returned no row")
        print("rows loaded:", count_row[0])
        print("executemany seconds:", round(executemany_seconds, 2))
        print("COPY seconds:", round(copy_seconds, 2))
        print("COPY was", round(executemany_seconds / copy_seconds), "times faster")

        # 3. Server-side cursor: fetch a big result in batches instead of all at once.
        new_order_count = 0
        with (
            conn.transaction(),
            conn.cursor(name="all_orders") as cur,
        ):
            cur.itersize = 5_000
            cur.execute("SELECT id, status FROM orders")
            # The leading underscore marks the order id as read but not used.
            for _order_id, status in cur:
                if status == "new":
                    new_order_count += 1
        print("new orders counted by streaming:", new_order_count)

        # 4. COPY TO STDOUT: export a query result to a CSV file in the project folder.
        output_file = Path("data/paid_orders_2025_03.csv")
        output_file.parent.mkdir(exist_ok=True)
        export_query = """
            COPY (
                SELECT id, customer_id, ordered_at
                FROM orders
                WHERE status = 'paid'
                  AND ordered_at >= '2025-03-01'
                  AND ordered_at <  '2025-04-01'
                ORDER BY id
            ) TO STDOUT WITH (FORMAT csv, HEADER)
        """
        with (
            conn.cursor() as cur,
            cur.copy(export_query) as copy,
            output_file.open("wb") as f,
        ):
            for chunk in copy:
                f.write(chunk)

        with output_file.open() as f:
            line_count = len(f.readlines())
        print("wrote", output_file, "with", line_count - 1, "data rows")


if __name__ == "__main__":
    main()
