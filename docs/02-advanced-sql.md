# 02 — Advanced SQL

**The idea.** With 200,000 orders loaded, you can ask real questions: who are the best customers, how does revenue move month to month, which products lead each category. This lab covers the SQL features that answer them: joins, CTEs, window functions, JSON queries, upserts and indexes.

**Where:** psql on pg1. Start from a fresh seed (step 1.8); if you are not sure, run that step again.

```bash
# Mac
docker compose exec pg1 psql -U lab -d labdb
```

Wait for `pg1 labdb=#`.

## 2.1 Joins: best customers, and customers with no orders

**The idea.** An inner `JOIN` keeps only rows that have a match on both sides. A `LEFT JOIN` keeps every row from the left table, even when nothing on the right matches.

```sql
-- pg1 psql
SELECT customers.id,
       customers.name,
       customers.country,
       count(DISTINCT orders.id)                     AS order_count,
       sum(order_items.qty * order_items.unit_price) AS revenue
FROM customers
JOIN orders      ON orders.customer_id = customers.id
JOIN order_items ON order_items.order_id = orders.id
WHERE orders.status <> 'cancelled'
GROUP BY customers.id, customers.name, customers.country
ORDER BY revenue DESC, customers.id
LIMIT 5;
```

Line by line:

1. The two `JOIN`s chain customers → their orders → those orders' lines. One row now exists per order line.
2. `WHERE orders.status <> 'cancelled'` drops cancelled orders before anything is added up. `<>` means "not equal".
3. `GROUP BY customers.id, …` collapses the rows to one per customer.
4. `count(DISTINCT orders.id)` counts different order ids. Plain `count(*)` would count order lines, because an order with three lines appears three times.
5. `ORDER BY revenue DESC, customers.id` sorts by revenue, highest first (`DESC` = descending). When two customers have equal revenue, the second key, `customers.id`, decides.
6. `LIMIT 5` returns only the first five rows.

**You should see:**

```
  id  |     name      | country | order_count | revenue
------+---------------+---------+-------------+----------
  403 | Customer 403  | ES      |          20 | 60518.77
  603 | Customer 603  | ES      |          20 | 60518.77
 1803 | Customer 1803 | ES      |          20 | 60518.77
 2003 | Customer 2003 | ES      |          20 | 60518.77
 3203 | Customer 3203 | ES      |          20 | 60518.77
(5 rows)
```

**What it means.** The arithmetic generator happened to give these five customers identical revenue. That is exactly why the second sort key is there: when rows tie, SQL returns them in no guaranteed order, so without `customers.id` the five names could come back in a different order on every run. Whenever you use `LIMIT` after `ORDER BY`, add a unique column as the last sort key.

Now find customers with no orders. Every seeded customer has 20, so add one who has none:

```sql
-- pg1 psql
INSERT INTO customers (email, name, country)
VALUES ('newbie@example.com', 'New Bie', 'MX');

SELECT customers.id, customers.name
FROM customers
WHERE NOT EXISTS (
    SELECT 1
    FROM orders
    WHERE orders.customer_id = customers.id
);
```

Line by line:

- `WHERE NOT EXISTS ( … )` keeps a customer only if the inner query finds **no** rows.
- The inner query looks for orders belonging to the current customer. `SELECT 1` is a convention: the query only has to say whether a row exists, so what it selects does not matter.

**You should see** `10001 | New Bie`.

The same question written with a `LEFT JOIN`:

```sql
-- pg1 psql
SELECT customers.id, customers.name
FROM customers
LEFT JOIN orders ON orders.customer_id = customers.id
WHERE orders.id IS NULL;
```

The `LEFT JOIN` keeps every customer. Where a customer has no order, the order columns come back as NULL, and `WHERE orders.id IS NULL` keeps only those rows. (`= NULL` never matches anything in SQL; testing for NULL needs `IS NULL`.) Both forms return the same answer. Lab 6 shows that Postgres can run the `NOT EXISTS` form more efficiently, so prefer it.

## 2.2 Monthly revenue with a CTE and window functions

**The idea.** Two features work together here.

- A **CTE** (`WITH name AS ( … )`) gives a sub-result a name, so a long query reads top to bottom in steps.
- A **window function** computes a value from other rows **related to the current row**, without collapsing them. `GROUP BY` turns many rows into one; a window function keeps every row and adds a column, such as "previous month's value" or "running total so far".

```sql
-- pg1 psql
WITH monthly AS (
    SELECT date_trunc('month', orders.ordered_at)        AS month_start,
           sum(order_items.qty * order_items.unit_price) AS revenue
    FROM orders
    JOIN order_items ON order_items.order_id = orders.id
    WHERE orders.status IN ('paid', 'shipped')
    GROUP BY date_trunc('month', orders.ordered_at)
)
SELECT to_char(month_start, 'YYYY-MM')                    AS month,
       revenue,
       revenue - lag(revenue) OVER (ORDER BY month_start)  AS change_from_previous,
       sum(revenue) OVER (ORDER BY month_start)            AS running_total
FROM monthly
ORDER BY month_start;
```

Line by line:

1. **Step 1, the CTE `monthly`:** one row per month with that month's revenue.
   - `date_trunc('month', orders.ordered_at)` rounds each timestamp down to the first moment of its month: 2025-03-17 14:05 becomes 2025-03-01 00:00. Every March order gets the same value, so `GROUP BY` that same expression puts them in one group.
2. **Step 2, the outer query,** reads from `monthly` as if it were a table.
   - `to_char(month_start, 'YYYY-MM')` formats the timestamp as text such as `2025-03`, purely for display.
   - `lag(revenue) OVER (ORDER BY month_start)` reads `revenue` from the **previous** row, with rows ordered by month. The first month has no previous row, so `lag` returns NULL there. `revenue - lag(revenue)` is the change from last month.
   - `sum(revenue) OVER (ORDER BY month_start)` is `sum` used as a window function. With `ORDER BY` inside `OVER`, it adds up revenue from the first row through the current row: a running total.
   - `OVER ( … )` is what turns a function into a window function. Its `ORDER BY` decides which row counts as "previous".
3. `ORDER BY month_start` sorts the final result chronologically by the real timestamp, not by the formatted text.

**You should see** 12 rows (first two and last shown):

```
  month  |   revenue   | change_from_previous | running_total
---------+-------------+----------------------+---------------
 2025-01 | 21224946.10 |                      |   21224946.10
 2025-02 | 19168768.12 |          -2056177.98 |   40393714.22
 ...
 2025-12 | 20150503.97 |           -388789.85 |  248832068.35
```

February is lower than January mostly because it has three fewer days. The last running total is the whole year's paid and shipped revenue.

## 2.3 Top products in each category

**The idea.** Ranking within groups is a window function too. `PARTITION BY` splits the rows into groups, and the window function restarts for each group.

```sql
-- pg1 psql
WITH product_revenue AS (
    SELECT products.attrs ->> 'category'                 AS category,
           products.sku,
           sum(order_items.qty * order_items.unit_price) AS revenue
    FROM products
    JOIN order_items ON order_items.product_id = products.id
    GROUP BY products.attrs ->> 'category', products.sku
),
ranked AS (
    SELECT category,
           sku,
           revenue,
           rank() OVER (PARTITION BY category ORDER BY revenue DESC) AS position
    FROM product_revenue
)
SELECT category, sku, revenue, position
FROM ranked
WHERE position <= 2
ORDER BY category, position;
```

Line by line:

1. **`product_revenue`:** total revenue per product. `products.attrs ->> 'category'` reads the `category` field out of the JSON column as text; step 2.4 explains `->>`.
2. **`ranked`:** `rank() OVER (PARTITION BY category ORDER BY revenue DESC)` numbers the products 1, 2, 3 … within each category, highest revenue first. Ties share a number.
3. **The final `SELECT`** keeps positions 1 and 2. The filter has to sit in a separate step: SQL computes window functions after `WHERE` has already run, so a `WHERE` in the same `SELECT` as `rank()` cannot see its result. A CTE (or subquery) runs first and lets the outer query filter on it.

A CTE can hold several named steps, separated by commas; each step can read the ones before it.

**You should see** 10 rows, two per category, starting:

```
 category |   sku    |  revenue   | position
----------+----------+------------+----------
 audio    | SKU-0039 | 2143024.31 |        1
 audio    | SKU-0024 | 2126616.70 |        2
```

## 2.4 Querying JSON data

**The idea.** A `jsonb` column stores a JSON document per row: useful for attributes that differ between products. Postgres has operators to reach inside it.

| Operator | Meaning | Example | Result |
| --- | --- | --- | --- |
| `->` | Get a field, as JSON | `attrs -> 'weight_kg'` | `0.2` (type `jsonb`) |
| `->>` | Get a field, as text | `attrs ->> 'category'` | `games` (type `text`) |
| `@>` | Does the left document **contain** the right one? | `attrs @> '{"color": "red"}'` | true or false |
| `?` | Does the document have this top-level key? | `attrs ? 'tags'` | true or false |

```sql
-- pg1 psql
SELECT sku,
       attrs ->> 'category'                    AS category,
       attrs -> 'weight_kg'                    AS weight_json,
       CAST(attrs ->> 'weight_kg' AS numeric)  AS weight_number
FROM products
ORDER BY id
LIMIT 3;
```

- `->>` returns text, and you cannot do arithmetic on text. `CAST(… AS numeric)` converts it to a number.

**You should see:**

```
   sku    | category | weight_json | weight_number
----------+----------+-------------+---------------
 SKU-0001 | games    | 0.2         |           0.2
 SKU-0002 | tools    | 0.3         |           0.3
 SKU-0003 | garden   | 0.4         |           0.4
```

The two weight columns look alike, but the first is JSON and the second is a number you can add, compare and sort numerically.

Filtering and changing JSON:

```sql
-- pg1 psql
SELECT count(*)
FROM products
WHERE attrs @> '{"category": "audio", "color": "black"}';

UPDATE products
SET attrs = jsonb_set(attrs, ARRAY['tags'], '["sale"]')
WHERE id <= 2
RETURNING sku, attrs;

SELECT sku
FROM products
WHERE attrs ? 'tags'
ORDER BY sku;
```

- `@>` finds products whose attributes include both `category: audio` and `color: black`, whatever other fields they have.
- `jsonb_set(document, path, new_value)` returns a copy of the document with one field set. The path is a list of keys, `ARRAY['tags']`, so it can reach into nested objects. A field that does not exist yet is added.
- `?` finds documents that have a `tags` key.

**You should see** `10`; then two updated rows whose `attrs` now include `"tags": ["sale"]`; then `SKU-0001` and `SKU-0002`.

Notice the key order in the updated rows: `{"tags": …, "color": …, "category": …, "weight_kg": …}`. `jsonb` does not keep the text you typed; it stores the document in a parsed form, with keys in its own order (shorter keys first). Use the `json` type instead only if you need the original text kept exactly.

**Indexing JSON.** A GIN index ("generalized inverted index") records which rows contain which keys and values, like the index at the back of a book. It speeds up `@>` and `?`:

```sql
-- pg1 psql
CREATE INDEX products_attrs_gin ON products USING gin (attrs);
```

**You should see** `CREATE INDEX`. With only 200 products, Postgres will still read the whole table rather than use the index; reading 200 rows is cheaper than an index lookup. Lab 6 explains that decision.

## 2.5 Upsert: insert, or update if it exists

**The idea.** Often you want to insert a row, or update it if a row with the same key already exists. Checking first and then inserting has a race: another session can insert between your check and your insert. `INSERT … ON CONFLICT` does both in one atomic step.

```sql
-- pg1 psql
INSERT INTO products (sku, name, price)
VALUES ('SKU-0001', 'Product 1 (v2)', 45.00),
       ('SKU-9999', 'Brand-new product', 15.00)
ON CONFLICT (sku) DO UPDATE
    SET name  = EXCLUDED.name,
        price = EXCLUDED.price
RETURNING id, sku, name, price;
```

Line by line:

1. `INSERT … VALUES` proposes two rows. `SKU-0001` already exists; `SKU-9999` does not.
2. `ON CONFLICT (sku)` says: if a proposed row collides with an existing row on the unique column `sku`, don't raise an error.
3. `DO UPDATE SET name = EXCLUDED.name, price = EXCLUDED.price` updates the existing row instead. `EXCLUDED` is Postgres's name for the proposed row that was kept out by the conflict, so `EXCLUDED.price` is the 45.00 you tried to insert.
4. `SKU-9999` has no conflict, so it is inserted normally.

**You should see:**

```
 id  |   sku    |       name        | price
-----+----------+-------------------+-------
   1 | SKU-0001 | Product 1 (v2)    | 45.00
 202 | SKU-9999 | Brand-new product | 15.00
(2 rows)
```

Row 1 kept its id and got the new name and price. The new product got id **202**, not 201: Postgres drew a number from the id counter for each proposed row before checking for conflicts, so the conflicting `SKU-0001` used up 201. This is the same gap effect as in step 1.3.

To silently skip conflicts instead:

```sql
-- pg1 psql
INSERT INTO products (sku, name, price)
VALUES ('SKU-0002', 'ignored', 1.00)
ON CONFLICT (sku) DO NOTHING;
```

**You should see** `INSERT 0 0`: zero rows inserted, no error.

## 2.6 Index the foreign keys

**The idea.** An index is a separate, sorted structure (a B-tree by default) that lets Postgres jump to matching rows instead of reading the whole table, like a phone book sorted by name. Postgres creates one automatically for every primary key and unique column, but **not** for foreign keys. Without one on `orders.customer_id`, the question "show customer 42's orders" reads all 200,000 orders. Deleting a customer has the same cost: Postgres must check that no order still points at them.

```sql
-- pg1 psql
CREATE INDEX orders_customer_id_idx     ON orders (customer_id);
CREATE INDEX order_items_product_id_idx ON order_items (product_id);
CREATE INDEX orders_ordered_at_idx      ON orders (ordered_at);
\di
```

- Each statement builds one index on the named column. The name is your choice; `table_column_idx` is a common convention.
- `orders_ordered_at_idx` is not for a foreign key; it speeds up date-range queries, used in Lab 6.
- `order_items.order_id` needs no new index: it is the first column of the table's two-column primary key, and an index on (order\_id, product\_id) also serves lookups by order\_id alone, the way a phone book sorted by last name, then first name, also works for a last name alone.

**You should see** `CREATE INDEX` three times, then a list of 10 indexes: your three new ones, `products_attrs_gin` from step 2.4, and six that Postgres created for the primary keys and unique columns (`customers_email_key`, `customers_pkey`, `order_items_pkey`, `orders_pkey`, `products_pkey`, `products_sku_key`).

How big are they?

```sql
-- pg1 psql
SELECT indexrelname                                AS index_name,
       pg_size_pretty(pg_relation_size(indexrelid)) AS size
FROM pg_stat_user_indexes
WHERE relname = 'orders'
ORDER BY indexrelname;
```

- `pg_stat_user_indexes` is a built-in view with one row per index; `relname` is the table, `indexrelname` the index, and `indexrelid` the index's internal id.
- `pg_relation_size(…)` returns a size in bytes; `pg_size_pretty(…)` turns it into readable units.

**You should see**, approximately:

```
       index_name       |  size
------------------------+---------
 orders_customer_id_idx | 1528 kB
 orders_ordered_at_idx  | 4408 kB
 orders_pkey            | 4408 kB
```

**What it means.** The customer index is about a third of the size of the others although it has the same 200,000 entries. Each customer id appears 20 times, and since Postgres 13 a B-tree stores a repeated value once, followed by the list of rows that have it (deduplication). The other two indexes hold 200,000 distinct values.

Leave psql:

```sql
-- pg1 psql
\q
```

---

Previous: [01 — SQL basics](01-sql-basics.md) · [Back to the README](../README.md) · Next: [03 — Python](03-python.md)
