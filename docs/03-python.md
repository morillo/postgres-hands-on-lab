# 03 — Python with psycopg 3 and SQLAlchemy 2.0

**The idea.** Applications talk to Postgres through a driver library. **psycopg 3** is the standard Python driver: you write SQL and it sends it, with your values, and hands back the rows. **SQLAlchemy** sits on top of a driver and lets you work with Python classes instead of SQL text (an ORM, object-relational mapper). You will use both, from scripts that run on your Mac and connect over the network to pg1 at `localhost:55432`.

**Where:** Mac terminal, in `pg-lab`. No psql in this lab.

## 3.0 Reset the data

```bash
# Mac
docker compose exec pg1 psql -U lab -d labdb -f /sql/seed.sql
```

**You should see** the same counts as step 1.8: `200 | 10000 | 200000 | 400001`. The indexes from Lab 2 stay; `TRUNCATE` empties tables but keeps their indexes.

## 3.1 Install the Python project

**The idea.** The repository is already a uv project: `pyproject.toml` lists the packages the scripts need, `uv.lock` pins their exact versions, and `.python-version` names the Python version. One command builds the project's own Python environment from those files.

```bash
# Mac
uv sync
```

`uv sync` reads `pyproject.toml` and `uv.lock`, downloads Python 3.13 if you don't have it, creates the project's private environment in `.venv/`, and installs exactly the versions listed in `uv.lock`. Two packages are for the scripts: `psycopg[binary]`, which means psycopg plus its precompiled `binary` extra that bundles the Postgres client library, so you need nothing from Homebrew; and `sqlalchemy`. The rest are the tools the repository's own checks use (Ruff, Pyright, pytest, pre-commit); the labs don't need them.

**You should see** `Creating virtual environment at: .venv`, then an install summary of `+ package==version` lines that includes `psycopg`, `psycopg-binary`, `sqlalchemy` and `typing-extensions` (psycopg 3.3.x and SQLAlchemy 2.1.x at the time of writing). If uv first downloads Python 3.13, it says so.

The project files:

| File | Purpose |
| --- | --- |
| `pyproject.toml` | The project description, its two packages and the development tools |
| `uv.lock` | The exact versions installed, so the setup can be reproduced |
| `.python-version` | Says `3.13`; uv reads it |
| `.venv/` | The project's private Python environment, created by `uv sync`. `uv run` uses it automatically, so you never activate it by hand. |

**How the scripts find the database.** The connection addresses are not written in the scripts. They live in `.env` (step 0.1) as `PG_DSN` and `SA_URL`, and every script reads them through one small helper module, `py/settings.py`:

```python
"""Connection settings for the lab scripts, read from environment variables.

The values live in the git-ignored .env file, copied from .env.example.
Run every script with `uv run --env-file .env python py/<script>.py`,
so that uv loads them into the environment first.
"""

import os


def require_env(name: str) -> str:
    """Return the value of an environment variable, or stop with a clear message.

    Args:
        name: Name of the environment variable to read.

    Returns:
        The variable's value.

    Raises:
        SystemExit: If the variable is missing or empty. Python prints the
            message and exits with status 1, without a traceback.
    """
    value = os.environ.get(name, "")
    if value == "":
        message = (
            f"{name} is not set. Create .env with 'cp .env.example .env', then run "
            "the script with 'uv run --env-file .env python py/<script>.py'."
        )
        raise SystemExit(message)
    return value


def pg_dsn() -> str:
    """Return the psycopg connection address, from PG_DSN."""
    return require_env("PG_DSN")


def sa_url() -> str:
    """Return the SQLAlchemy database URL, from SA_URL."""
    return require_env("SA_URL")
```

Line by line:

1. The text in triple quotes at the top of the file, and right under each `def`, is a **docstring**: a description of the module or function that editors show when you hover over its name.
2. **`os.environ.get(name, "")`** reads one environment variable, or gives empty text if it is not set.
3. **`name: str`** and **`-> str`** are **type hints**: `name` is text, and the function returns text. Python does not enforce them when the script runs; a type checker such as Pyright (the engine behind VS Code's Pylance) uses them to catch mistakes before the code runs.
4. **`raise SystemExit(message)`** stops the script and prints only the message, with no Python traceback. So if you forget `.env`, you see:

   ```
   PG_DSN is not set. Create .env with 'cp .env.example .env', then run the script with 'uv run --env-file .env python py/<script>.py'.
   ```

5. **`pg_dsn()`** returns `PG_DSN`, the address the psycopg scripts use; **`sa_url()`** returns `SA_URL`, the one SQLAlchemy uses.

Every script in this lab runs as `uv run --env-file .env python py/<script>.py`. `--env-file .env` loads each `NAME=value` line of `.env` into the environment of that one command; `uv run` then starts the script with the project's Python and packages.

## 3.2 Connect and query

The script is in the repository at `py/01_basics.py`:

```python
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
```

Run it:

```bash
# Mac
uv run --env-file .env python py/01_basics.py
```

**Line by line:**

1. **The DSN** (data source name) is the connection address, read as `postgresql://user:password@host:port/database`. `pg_dsn()` (step 3.1) returns the value of `PG_DSN` from `.env`, `postgresql://lab:lab@localhost:55432/labdb`. Keeping it in `.env` lets you point the script elsewhere, or change the password, without editing the code.

   **`def main() -> None:`** holds the script's work in one function; `-> None` says it returns nothing. The last two lines, `if __name__ == "__main__":` and `main()`, call it only when the file is run as a script, not when another file imports it. All four scripts in this lab are built this way.
2. **`with psycopg.connect(dsn) as conn:`** opens one connection to the server. The `with` block manages it: when the block ends normally the work is committed; if an exception escapes, it is rolled back; either way the connection is closed.
3. **`conn.cursor()`** creates a cursor, the object that runs statements and holds their results. `cur.execute(sql)` sends a statement; `cur.fetchone()` returns the next row, `cur.fetchall()` all remaining rows. The cursor's own `with` block closes it afterwards.
4. **Rows are tuples by default.** `row[0]` is the first column. `cur.fetchone()` returns `None` when no row is left, so the script checks `if row is None:` before reading `row[0]`. `count(*)` always returns exactly one row, so the check never fires here; it makes that fact visible to a reader and to the type checker.
5. **Parameters.** `%s` in the SQL marks a spot for a value, and the values go separately, as a tuple: `(country, 3)`. This is not Python string formatting. psycopg sends the SQL text and the values to the server separately, and the server never parses the values as SQL.
6. **`row_factory=dict_row`** makes rows come back as dictionaries keyed by column name. The query text is written as two strings side by side; Python joins adjacent strings into one, which keeps each line short.

   **Named parameters.** Section 3 uses a second placeholder style. Instead of `%s`, the placeholder carries a name: `%(product_id)s`. Read it as three parts: `%(` opens the placeholder, `product_id` is the name you choose, and `)s` closes it. The trailing `s` is part of psycopg's placeholder syntax, not a type: it stays `s` whether the value is a number, text or a date. The values then go in a dictionary whose keys are those names, `{"product_id": 7}`, and psycopg matches each placeholder to its value **by name**, not by position.

   |  | Positional `%s` | Named `%(name)s` |
   | --- | --- | --- |
   | Values passed as | A tuple: `(country, 3)` | A dictionary: `{"product_id": 7}` |
   | Matched by | Order: 1st `%s` gets the 1st value | Name: `%(product_id)s` gets the value under `"product_id"` |
   | Same value used twice | Must be listed twice | One entry, written `%(name)s` twice in the SQL |
   | Best for | One or two values | Several values, where names make the query readable |

   For example, `UPDATE products SET price = %(price)s WHERE sku = %(sku)s AND price <> %(price)s` uses `price` twice but needs only `{"price": 45.00, "sku": "SKU-0001"}`. One query must use one style, not a mix. And because `%` starts a placeholder, a literal percent sign in a query that has parameters is written `%%`, for example `name LIKE 'Customer 1%%'`.
7. **The injection attempt.** The input `VE' OR '1'='1` is designed to break out of a quoted string. If you had pasted it into the SQL text with an f-string, the query would become `WHERE country = 'VE' OR '1'='1'` and match every customer. Sent as a parameter, it is just a strange country code, and nothing matches.

**You should see** (the version number is yours: 17 followed by four digits):

```
server version: 170006
orders: 200000
tuple row: (2, 'Customer 2')
tuple row: (10, 'Customer 10')
tuple row: (18, 'Customer 18')
dict row: {'sku': 'SKU-0007', 'price': Decimal('264.99'), 'category': 'tools'}
rows matched by the injection attempt: 0
```

**What it means.** The price came back as `Decimal('264.99')`, Python's exact decimal type, never a `float`, so money keeps its exact value. Postgres types map to Python types: `numeric` → `Decimal`, `jsonb` → dict and list, `timestamptz` → a `datetime` with a time zone. Parameters only work for **values**. If a table or column name must be chosen at run time, build it with `psycopg.sql.Identifier`, which quotes it safely; never paste it into the SQL text yourself.

## 3.3 Transactions from Python

**The idea.** psycopg has two modes, and the default one surprises people. With the default, the first statement you run silently opens a transaction, and it stays open until you commit. The recommended pattern is **autocommit mode** plus explicit `with conn.transaction():` blocks, so every transaction's start and end is visible in the code.

The script is in the repository at `py/02_transactions.py`:

```python
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
```

Run it:

```bash
# Mac
uv run --env-file .env python py/02_transactions.py
```

**Line by line:**

1. **`def get_price(conn: psycopg.Connection[TupleRow], sku: str) -> Decimal:`** The type hints say that `conn` is a psycopg connection whose rows are tuples, `sku` is text, and the function returns a `Decimal`. If no product has that SKU, `fetchone()` returns `None`, and the function raises `LookupError` with a clear message instead of failing on `row[0]`.
2. **`conn.execute(sql, params)`** is a shortcut: it creates a cursor, runs the statement and returns the cursor, so `.fetchone()` can follow directly.
3. **`conn.info.transaction_status.name`** reports the connection's state: `IDLE` (no transaction open) or `INTRANS` (a transaction is open).
4. **Part 1** shows the default mode: after a plain `SELECT`, the status is already `INTRANS`. A transaction opened that nobody asked for.
5. **Part 2** opens the connection with `autocommit=True`: each statement commits on its own, and the status stays `IDLE`.
6. **Block A:** `with conn.transaction():` sends `BEGIN` at the start and `COMMIT` at the end of the block.
7. **Block B:** the second `UPDATE` sets price to -1, which breaks the `CHECK (price > 0)` rule. psycopg raises `psycopg.errors.CheckViolation`; the block sends `ROLLBACK`, so the `+100` from the first update is undone too. `error.diag.constraint_name` reads the name of the rule that failed from the server's error details.
8. **Block C:** a `transaction()` block inside another becomes a **savepoint**, a marker inside a transaction you can roll back to. The insert of an order for customer 999999 fails the foreign key; only the inner block is undone, and the outer `+1` still commits.

**You should see:**

```
default autocommit: False
status after a SELECT: INTRANS
status after a SELECT: IDLE
start price: 190.99
status inside block: INTRANS
after committed block: 191.99
rolled back because: products_price_check
after failed block: 191.99
inner savepoint rolled back; outer block continues
after savepoint demo: 192.99
restored price: 190.99
```

**What it means.** The first two lines are the lesson. In default mode, a connection that ran one `SELECT` and then sits waiting shows up in the server as `idle in transaction`. If it has written anything, or uses a stricter isolation level, it also stops VACUUM from cleaning up (Lab 5 shows this). And in default mode, a `with conn.transaction():` block written inside that silent transaction is only a savepoint, so it does not actually commit. Use `autocommit=True` and explicit blocks.

psycopg names its exception classes after the server's error conditions: `UniqueViolation`, `ForeignKeyViolation`, `CheckViolation`, `SerializationFailure` (Lab 4), `DeadlockDetected`. Catch the specific one you expect.

## 3.4 Loading and reading lots of rows

**The idea.** Sending rows one `INSERT` at a time is slow, because each statement is parsed and executed separately. `COPY` is Postgres's bulk path: one statement, with all the rows streamed after it. Reading has the mirror-image problem: a normal query loads the entire result into Python memory before your loop starts. A **server-side cursor** keeps the result on the server and fetches it in batches.

The script is in the repository at `py/03_bulk.py`:

```python
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
```

Run it, then print the first three lines of the CSV file it wrote:

```bash
# Mac
uv run --env-file .env python py/03_bulk.py
head -3 data/paid_orders_2025_03.csv
```

**Line by line:**

1. **Test data:** a list of 50,000 tuples `(id, label, bucket)`. `rows: list[tuple[int, str, int]] = []` starts an empty list, with a type hint saying what it will hold. `i % 7` is the remainder of i divided by 7, giving buckets 0–6. `f"event-{i}"` builds text such as `event-42`.
2. **`time.perf_counter()`** reads a high-precision clock; subtracting two readings gives elapsed seconds.
3. **`with (conn.transaction(), conn.cursor() as cur):`**, written over several lines, enters several `with` blocks in one statement, in order: first the transaction, then the cursor. They close in reverse order when the block ends, so the cursor closes before the transaction commits. It means the same as writing one `with` inside the other, with less indentation. **`cur.executemany(sql, rows)`** runs the `INSERT` once per tuple.
4. **`cur.copy("COPY events (…) FROM STDIN")`** starts a `COPY`: "read rows for these columns from the input stream". `copy.write_row(row)` sends one row. When the `with` block ends, psycopg signals the end of the data.
5. **`conn.cursor(name="all_orders")`**: giving a cursor a name makes it a server-side cursor. `cur.itersize = 5_000` sets the batch size; the `for` loop then receives rows 5,000 at a time. A server-side cursor only lives inside a transaction, hence the `conn.transaction()` in the same `with`. Each row is unpacked into two names, `_order_id` and `status`; the leading underscore marks the id as read but not used.
6. **`COPY ( query ) TO STDOUT WITH (FORMAT csv, HEADER)`** runs a query and streams the result as CSV, header line first. Each `chunk` is a piece of that stream, written as-is to the file. `Path("data/…")` is relative to the current folder, so the file lands in `pg-lab/data/`; `mkdir(exist_ok=True)` creates the folder if needed.
7. **Counting rows:** read all lines of the file and subtract 1 for the header.

**You should see** (the timings are yours):

```
rows loaded: 50000
executemany seconds: 0.54
COPY seconds: 0.08
COPY was 7 times faster
new orders counted by streaming: 2000
wrote data/paid_orders_2025_03.csv with 1197 data rows
id,customer_id,ordered_at
32503,1258,2025-03-01 01:29:31+00
32504,9177,2025-03-01 01:32:08+00
```

**What it means.** `COPY` is several times faster even though psycopg already batches `executemany` internally. Through Docker Desktop's network layer on a Mac the gap is often wider. Use `executemany` for a few hundred rows, or when you need `ON CONFLICT`; use `COPY` for anything large. The `events` table is dropped in [the cleanup section](cleanup-and-troubleshooting.md#cleanup).

## 3.5 The SQLAlchemy ORM

**The idea.** An ORM maps each table to a Python class and each row to an object. You write Python; SQLAlchemy generates the SQL and runs it through psycopg. The trade-off: less SQL to write, but less visibility into what runs, and it is easy to send far more queries than you meant to.

The script is in the repository at `py/04_orm.py`:

```python
"""Lab 3.5: SQLAlchemy 2.0 ORM. Map the existing tables to Python classes, query, and write."""

from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import ForeignKey, create_engine, func, select
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, relationship

from settings import sa_url


class Base(DeclarativeBase):
    """Common parent class of every mapped class."""


class Customer(Base):
    """One row of the customers table."""

    __tablename__ = "customers"
    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str]
    name: Mapped[str]
    country: Mapped[str]
    orders: Mapped[list["Order"]] = relationship(back_populates="customer", order_by="Order.id")


class Product(Base):
    """One row of the products table."""

    __tablename__ = "products"
    id: Mapped[int] = mapped_column(primary_key=True)
    sku: Mapped[str]
    name: Mapped[str]
    price: Mapped[Decimal]
    attrs: Mapped[dict[str, Any]] = mapped_column(JSONB)


class Order(Base):
    """One row of the orders table."""

    __tablename__ = "orders"
    id: Mapped[int] = mapped_column(primary_key=True)
    customer_id: Mapped[int] = mapped_column(ForeignKey("customers.id"))
    status: Mapped[str]
    ordered_at: Mapped[datetime]
    customer: Mapped[Customer] = relationship(back_populates="orders")
    items: Mapped[list["OrderItem"]] = relationship(cascade="all, delete-orphan")


class OrderItem(Base):
    """One row of the order_items table: one product in one order."""

    __tablename__ = "order_items"
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id"), primary_key=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"), primary_key=True)
    qty: Mapped[int]
    unit_price: Mapped[Decimal]
    product: Mapped[Product] = relationship()


def main() -> None:
    """Query through the ORM, follow relationships, then insert and remove one order."""
    engine = create_engine(sa_url())

    # 1. A query built in Python: revenue per country for shipped orders.
    revenue_by_country = (
        select(Customer.country, func.sum(OrderItem.qty * OrderItem.unit_price).label("revenue"))
        .join(Customer.orders)
        .join(Order.items)
        .where(Order.status == "shipped")
        .group_by(Customer.country)
        .order_by(Customer.country)
    )
    print("SQL that will be sent:")
    print(revenue_by_country.compile(engine))
    print()

    with Session(engine) as session:
        for row in session.execute(revenue_by_country):
            print(row.country, row.revenue)

        # 2. Follow relationships from one object to related objects.
        customer = session.get_one(Customer, 42)
        first_order = customer.orders[0]
        first_item = first_order.items[0]
        print()
        print(customer.name, "has", len(customer.orders), "orders")
        print(
            "first order has",
            len(first_order.items),
            "item(s); first product:",
            first_item.product.sku,
        )

    # 3. Remove leftovers from an earlier interrupted run, so the script can be re-run.
    with (
        Session(engine) as session,
        session.begin(),
    ):
        leftover = session.scalar(select(Customer).where(Customer.email == "orm@example.com"))
        if leftover is not None:
            for order in leftover.orders:
                session.delete(order)
            session.delete(leftover)

    # 4. Write: one customer, one order, two order lines, in one transaction.
    with (
        Session(engine) as session,
        session.begin(),
    ):
        new_customer = Customer(email="orm@example.com", name="Orm User", country="DE")
        keyboard = session.get_one(Product, 1)
        headphones = session.get_one(Product, 2)
        new_order = Order(
            customer=new_customer, status="new", ordered_at=datetime.now().astimezone()
        )
        new_order.items = [
            OrderItem(product=keyboard, qty=2, unit_price=keyboard.price),
            OrderItem(product=headphones, qty=1, unit_price=headphones.price),
        ]
        session.add(new_order)
        session.flush()
        new_customer_id = new_customer.id
        new_order_id = new_order.id
    print()
    print("inserted customer", new_customer_id, "and order", new_order_id)

    # 5. Clean up so the lab stays repeatable.
    with (
        Session(engine) as session,
        session.begin(),
    ):
        session.delete(session.get_one(Order, new_order_id))
        session.delete(session.get_one(Customer, new_customer_id))
    print("cleaned up")


if __name__ == "__main__":
    main()
```

Run it:

```bash
# Mac
uv run --env-file .env python py/04_orm.py
```

**Line by line, the mapping (top half):**

1. **The URL** `postgresql+psycopg://…` means "PostgreSQL, through the psycopg (version 3) driver". A plain `postgresql://` would make SQLAlchemy look for the older psycopg2.
2. **`class Base(DeclarativeBase)`** is the common parent class for all mapped classes. Its docstring is its whole body; a class needs no `pass` when it has one.
3. **Each class maps one existing table**, named by `__tablename__`. The script never creates tables; they already exist from Lab 1.
4. **`id: Mapped[int] = mapped_column(primary_key=True)`**: `Mapped[int]` declares a column holding an `int`; `mapped_column(...)` adds details such as "this is the primary key". A bare `email: Mapped[str]` is a plain text column with no extra details. `Mapped[dict[str, Any]]` on `attrs` says the `jsonb` column comes back as a dictionary with text keys and values of any type.
5. **`ForeignKey("customers.id")`** tells SQLAlchemy how the tables connect, so it can write join conditions for you.
6. **`relationship(...)`** adds a Python attribute that holds related objects rather than a column value. `Customer.orders` is a list of that customer's `Order` objects; `back_populates="customer"` links it with `Order.customer` going the other way. `order_by="Order.id"` loads the list sorted by order id, so "first order" means the lowest id. `cascade="all, delete-orphan"` on `Order.items` means deleting an order through the ORM deletes its items too.

**Line by line, the work (bottom half):**

1. **`create_engine(sa_url())`** creates the engine, which manages a pool of connections. `sa_url()` returns `SA_URL` from `.env` (step 3.1).
2. **Part 1:** `select(...)` builds a query as a Python object; `.join(Customer.orders)` joins along the relationship, so you don't write the `ON` condition. `func.sum(...)` produces SQL's `sum()`; `.label("revenue")` names the result column. `.compile(engine)` prints the SQL it will send.
3. **`Session(engine)`** is a unit of work: it keeps track of the objects you load and change. `session.execute(query)` runs a query; each row's columns are available by name, `row.country`.
4. **Part 2:** `session.get_one(Customer, 42)` loads the customer whose primary key is 42, and raises an error if there is none (`session.get` would return `None` instead). Reading `customer.orders`, then `.items`, then `.product` makes SQLAlchemy run a separate query each time to load the related objects (lazy loading).
5. **Parts 3–5:** `with (Session(engine) as session, session.begin()):`, written over several lines like the `with` blocks in step 3.4, opens a session and starts one transaction in it: it commits when the block ends and rolls back on an exception. `session.add(new_order)` schedules the new objects to be inserted; the customer and items come along because they are attached to the order. `session.flush()` sends the pending `INSERT`s immediately, so Postgres assigns the ids now. The script copies the ids into plain variables **inside** the block: after the commit, SQLAlchemy treats loaded objects as possibly out of date ("expired"), and once the session closes, reading `new_customer.id` would raise an error.

**You should see** (the two inserted ids are yours):

```
SQL that will be sent:
SELECT customers.country, sum(order_items.qty * order_items.unit_price) AS revenue
FROM customers JOIN orders ON customers.id = orders.customer_id JOIN order_items ON orders.id = order_items.order_id
WHERE orders.status = %(status_1)s::VARCHAR GROUP BY customers.country ORDER BY customers.country

BR 28552912.35
CA 34564410.01
DE 28101181.70
ES 39019327.97
JP 19824567.64
MX 17974721.72
US 33280965.60
VE 32562370.33

Customer 42 has 20 orders
first order has 1 item(s); first product: SKU-0074

inserted customer 10001 and order 200002
cleaned up
```

**What it means.**

- In the generated SQL, `%(status_1)s` is the psycopg named-parameter placeholder from step 3.2: SQLAlchemy sends `'shipped'` as a parameter, never pasted into the text. `::VARCHAR` is Postgres's short form of `CAST(… AS varchar)`; SQLAlchemy adds it to state the parameter's type.
- The order id is 200002 rather than 200001 because the failed insert in the savepoint demo (step 3.3) used up 200001.
- Loading customer 42, their orders, the first order's items and that item's product took four separate queries. In a loop over many customers that becomes one query per customer per relationship, the "N+1 queries" problem. In real code, ask for related objects up front with `options(selectinload(Customer.orders))`, which loads them all in one extra query.

---

Previous: [02 — Advanced SQL](02-advanced-sql.md) · [Back to the README](../README.md) · Next: [04 — MVCC](04-mvcc.md)
