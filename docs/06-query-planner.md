# 06 — The query planner

**The idea.** SQL says **what** you want, not **how** to get it. For every query, the **planner** considers different ways to run it: read the whole table, or use an index? Which of two tables to read first? Which join method? It estimates the cost of each option and picks the cheapest. Its estimates rely on **statistics** about your data, so when the statistics are wrong, it picks a bad plan. Most slow queries are a bad estimate somewhere.

In this lab you read plans, compare the planner's estimates with reality, and watch its choices change as indexes and statistics change.

**Where:** Mac terminal for 6.0, then psql on pg1.

## 6.0 Reset the data and connect

```bash
# Mac
docker compose exec pg1 psql -U lab -d labdb -f /sql/seed.sql
docker compose exec pg1 psql -U lab -d labdb
```

The first command reloads the dataset (same counts as step 1.8); the second opens psql. Wait for `pg1 labdb=#`. Make sure the indexes from step 2.6 exist; `IF NOT EXISTS` skips any that are already there, with a harmless `NOTICE`:

```sql
-- pg1 psql
CREATE INDEX IF NOT EXISTS orders_customer_id_idx     ON orders (customer_id);
CREATE INDEX IF NOT EXISTS order_items_product_id_idx ON order_items (product_id);
CREATE INDEX IF NOT EXISTS orders_ordered_at_idx      ON orders (ordered_at);
```

## 6.1 Read a plan

`EXPLAIN` in front of a query shows the plan without running the query.

```sql
-- pg1 psql
EXPLAIN SELECT * FROM orders WHERE status = 'new';
```

**You should see** (the `rows=` number is yours, close to 2000):

```
                         QUERY PLAN
-------------------------------------------------------------
 Seq Scan on orders  (cost=0.00..3982.00 rows=1913 width=31)
   Filter: (status = 'new'::text)
```

How to read it:

| Part | Meaning |
| --- | --- |
| `Seq Scan on orders` | The operation: a sequential scan, reading every page of the table from start to end |
| `cost=0.00..3982.00` | Estimated cost, in the planner's own units: before the first row is returned .. after the last. The unit is roughly "reading one page in order costs 1.0". The numbers only mean something compared with other plans. |
| `rows=1913` | How many rows the planner expects this step to return |
| `width=31` | Expected average row size in bytes |
| `Filter: (status = 'new'::text)` | The condition tested on every row read. `'new'::text` is Postgres's short way of writing `CAST('new' AS text)`; plans always show this form. |

A plan is a tree: in bigger plans each step feeds the step above it, and indentation shows which feeds which.

**Where the cost comes from.** You can recompute it from the table's size and three cost settings:

```sql
-- pg1 psql
SELECT relpages,
       reltuples,
       relpages  * CAST(current_setting('seq_page_cost')     AS float8)
     + reltuples * CAST(current_setting('cpu_tuple_cost')    AS float8)
     + reltuples * CAST(current_setting('cpu_operator_cost') AS float8) AS seq_scan_cost
FROM pg_class
WHERE relname = 'orders';
```

- `pg_class` is the catalog of tables and indexes. `relpages` is the table's size in 8 KB pages and `reltuples` its row count, both recorded by `ANALYZE`.
- `current_setting('name')` returns a setting's value as text; `CAST(… AS float8)` converts it to a number. `float8` is a double-precision floating-point number.

**You should see** `1482 | 200000 | 3982`.

**What it means.** 1,482 pages × 1.0 (`seq_page_cost`, the cost of reading one page in order) + 200,000 rows × 0.01 (`cpu_tuple_cost`, the cost of handling one row) + 200,000 × 0.0025 (`cpu_operator_cost`, the cost of evaluating one `=` comparison) = 3,982. Every plan's cost is built from estimates like these.

## 6.2 Estimates versus reality

`EXPLAIN ANALYZE` runs the query for real and shows the actual numbers next to the estimates. `BUFFERS` adds how many pages it touched.

```sql
-- pg1 psql
EXPLAIN (ANALYZE, BUFFERS) SELECT * FROM orders WHERE status = 'new';
```

**You should see** (times yours):

```
 Seq Scan on orders  (cost=0.00..3982.00 rows=1913 width=31) (actual time=0.010..11.768 rows=2000 loops=1)
   Filter: (status = 'new'::text)
   Rows Removed by Filter: 198000
   Buffers: shared hit=1482
 Planning Time: 0.021 ms
 Execution Time: 11.858 ms
```

| Part | Meaning |
| --- | --- |
| `actual time=0.010..11.768` | Milliseconds until the first row .. until the last |
| `rows=2000` (in the actual part) | Rows really returned. Compare with the estimated 1913. |
| `loops=1` | How many times this step ran. Inside a join a step can run once per outer row; then times and rows are per loop. |
| `Rows Removed by Filter: 198000` | Rows read and thrown away |
| `Buffers: shared hit=1482` | 1,482 pages were found in Postgres's memory cache (`hit`). Pages fetched from disk would show as `read=`. |

Sometimes two more lines appear under the plan, `Planning:` and `Buffers: shared hit=12` beneath it. They count pages the **planner** read while choosing the plan: the system catalogs that describe the table, its indexes and its statistics. They show up when Postgres had to reload that information, for example right after `ANALYZE` replaced the statistics. On the next run the information is cached again and the lines disappear.

Because `ANALYZE` really runs the query, wrap an `UPDATE` or `DELETE` in `BEGIN; … ROLLBACK;` before you `EXPLAIN ANALYZE` it.

**What it means.** Comparing estimated rows with actual rows, step by step, is the single most useful habit in query tuning. Here 1,913 versus 2,000 is close. A gap of 10× or more is where bad plans come from.

**Where the 1,913 came from.** The planner multiplies the table's row count by the fraction of rows it believes match. That fraction comes from statistics:

```sql
-- pg1 psql
SELECT n_distinct, most_common_vals, most_common_freqs
FROM pg_stats
WHERE tablename = 'orders' AND attname = 'status';
```

`pg_stats` shows the statistics `ANALYZE` collected for each column (`attname` is the column name).

**You should see** `n_distinct` = `4` (four different values), `most_common_vals` = `{shipped,paid,cancelled,new}`, and `most_common_freqs` close to `{0.90,0.07,0.02,0.01}`.

**What it means.** `ANALYZE` does not read every row; it reads a **random** sample of 30,000. Whatever share of `new` rows lands in that sample is what the planner believes. If about 0.96% of the sample were `new`, the estimate is 0.96% × 200,000 ≈ 1,913 rows; if 1.02% were, it is ≈ 2,047. The true share is exactly 1%, so every estimate lands close to 2,000 but rarely exactly on it. Because the sample is random, your number differs from this doc's and changes each time `ANALYZE` runs (the seed script runs it, and so does autovacuum). To watch the estimate move, take a new sample and look at the plan again:

```sql
-- pg1 psql
ANALYZE orders;
EXPLAIN SELECT * FROM orders WHERE status = 'new';
```

**You should see** a `rows=` estimate close to 2,000, usually different from the one before.

## 6.3 When does an index help?

```sql
-- pg1 psql
CREATE INDEX IF NOT EXISTS orders_status_idx ON orders (status);
EXPLAIN SELECT * FROM orders WHERE status = 'new';
EXPLAIN SELECT * FROM orders WHERE status = 'shipped';
```

**You should see** two different plans:

- For `new` (1% of rows): a `Bitmap Heap Scan on orders`, fed by a `Bitmap Index Scan on orders_status_idx`.
- For `shipped` (90% of rows): still a `Seq Scan on orders`, estimating about 180,000 rows.

**What it means.** An index finds **which** rows match, but each match then needs a jump to wherever that row lives in the table. Jumping around costs more than reading in order: the planner prices a random page read at 4.0 (`random_page_cost`) against 1.0 for a sequential one. For 1% of the rows, jumping wins. For 90%, jumping to nearly every row costs far more than simply reading the table front to back, so the planner ignores the index. An index pays off when a query needs a small fraction of the table.

Now look at what the `new` plan really touched:

```sql
-- pg1 psql
EXPLAIN (ANALYZE, BUFFERS, TIMING OFF) SELECT * FROM orders WHERE status = 'new';
```

`TIMING OFF` leaves out the per-step timing to keep the output short.

**You should see** a line `Heap Blocks: exact=1482`.

**What it means.** The index plan still read all 1,482 table pages. The generator made every 100th order `new`, so `new` rows sit on every single page. The index found 2,000 rows, but they were spread over the whole table. Where the matching rows sit matters as much as how many there are. (The statistics track this too: `pg_stats.correlation` measures how closely a column's sort order follows the physical order of the rows.)

## 6.4 The ways to read a table

Run each and look at the first line of each plan:

```sql
-- pg1 psql
EXPLAIN SELECT * FROM orders WHERE id = 42;
EXPLAIN SELECT * FROM orders WHERE customer_id = 42;
EXPLAIN SELECT * FROM orders WHERE ordered_at >= '2025-06-01' AND ordered_at < '2025-06-02';
EXPLAIN SELECT id FROM orders WHERE id < 1000;
```

**You should see**, in order:

1. `Index Scan using orders_pkey`: one row, found through the primary-key index.
2. `Bitmap Heap Scan`, fed by `Bitmap Index Scan on orders_customer_id_idx`: the customer's 20 orders, scattered through the table.
3. `Index Scan using orders_ordered_at_idx`: one day of orders. Orders were created in date order, so they sit next to each other in the table.
4. `Index Only Scan using orders_pkey`: the query only needs `id`, which is in the index itself.

| Method | How it works | Chosen when |
| --- | --- | --- |
| Seq Scan | Read every page in order | A large share of the rows match, or there is no useful index |
| Index Scan | Walk the index, and for each match fetch the row from the table | Few rows, or rows wanted in index order |
| Bitmap Index Scan + Bitmap Heap Scan | First collect all matching row locations from the index into a map of pages; then read those pages once each, in physical order | A moderate number of rows scattered across the table. Can also combine two indexes. |
| Index Only Scan | Answer from the index alone, without visiting the table | Every column the query needs is in the index |

**Why index-only scans depend on VACUUM.** An index entry has no `xmin`/`xmax` (Lab 4), so the index alone cannot say whether a row is visible to your snapshot. Postgres can skip the table only for pages that the **visibility map** marks as "every row here is visible to everyone". Only VACUUM sets those marks.

You can't see this on `orders`: autovacuum vacuums it soon after the seed loads it (since Postgres 13 it also runs after large inserts), so by the time you get here its pages are already marked. Instead, use a small throwaway table with autovacuum switched off, so nothing changes it behind your back, however long you take between steps:

```sql
-- pg1 psql
CREATE TABLE vm_demo (id int PRIMARY KEY, note text) WITH (autovacuum_enabled = false);
INSERT INTO vm_demo SELECT n, 'row ' || n FROM generate_series(1, 100000) AS n;
ANALYZE vm_demo;
```

- `WITH (autovacuum_enabled = false)` stops autovacuum for this table only.
- `ANALYZE vm_demo` collects statistics so the planner knows the table's size, but it does **not** set visibility marks; only VACUUM does.

**You should see** `CREATE TABLE`, `INSERT 0 100000`, `ANALYZE`. Now compare the same query before and after a VACUUM:

```sql
-- pg1 psql
EXPLAIN (ANALYZE, COSTS OFF, TIMING OFF, SUMMARY OFF) SELECT id FROM vm_demo WHERE id < 1000;
VACUUM vm_demo;
EXPLAIN (ANALYZE, COSTS OFF, TIMING OFF, SUMMARY OFF) SELECT id FROM vm_demo WHERE id < 1000;
```

`COSTS OFF`, `TIMING OFF` and `SUMMARY OFF` remove the cost numbers and timings, leaving only the plan's shape and counts.

**You should see** `Index Only Scan using vm_demo_pkey` both times, with `Heap Fetches: 999` before the `VACUUM` and `Heap Fetches: 0` after.

**What it means.** The new table had no visibility marks, so the "index-only" scan still went to the table for all 999 rows to check that each was visible. After VACUUM marked the pages all-visible, it never touched the table. That is one more reason autovacuum matters: on `orders` it had already done this for you. You can see when with `SELECT last_autovacuum FROM pg_stat_user_tables WHERE relname = 'orders';`

Drop the demo table:

```sql
-- pg1 psql
DROP TABLE vm_demo;
```

## 6.5 The ways to join tables

**The idea.** Postgres has three methods for joining two tables. It picks one by comparing their costs.

| Method | How it works | Good when |
| --- | --- | --- |
| Nested Loop | For each row on one side, look up matching rows on the other side, usually through an index | One side is small and the other has an index on the join column |
| Hash Join | Read the smaller side into an in-memory hash table keyed on the join column; then read the larger side and look each row up | Both sides are large and unsorted, and the condition is `=` |
| Merge Join | Read both sides already sorted on the join column and walk them in step, like merging two sorted lists | Both sides are already sorted, for example by an index |

```sql
-- pg1 psql
EXPLAIN (COSTS OFF)
SELECT customers.name, orders.id
FROM customers
JOIN orders ON orders.customer_id = customers.id
WHERE customers.id = 42;

EXPLAIN (COSTS OFF)
SELECT orders.id, order_items.qty
FROM orders
JOIN order_items ON order_items.order_id = orders.id;
```

**You should see:**

- First query: a `Nested Loop`. It finds the one customer through `customers_pkey`, then that customer's orders through `orders_customer_id_idx`.
- Second query: a `Hash Join`. It builds a hash table from a `Seq Scan on orders`, then streams a `Seq Scan on order_items` through it. Every row of both tables is needed, so reading both in full is cheapest.

To see a merge join, discourage hash joins for one query:

```sql
-- pg1 psql
SET enable_hashjoin = off;
EXPLAIN (COSTS OFF)
SELECT customers.country, count(*)
FROM customers
JOIN orders ON orders.customer_id = customers.id
GROUP BY customers.country;
RESET enable_hashjoin;
```

- `SET enable_hashjoin = off` makes hash joins look extremely expensive to the planner for the rest of this session. It does not forbid them outright. Use these switches only to investigate, never in application code.
- `RESET enable_hashjoin` restores the default.

**You should see** a `Merge Join` with `Merge Cond: (orders.customer_id = customers.id)`. Both inputs come from indexes that are already sorted by customer id. You will also see `Gather Merge` and `Workers Planned: 1` or `2`, with a `Partial HashAggregate` and a `Finalize GroupAggregate` above it: Postgres split the work across parallel worker processes and combined their partial counts at the end. The number of workers depends on how many CPUs Docker gives the container.

**The two ways to find customers with no orders**, from step 2.1:

```sql
-- pg1 psql
EXPLAIN (COSTS OFF)
SELECT customers.id
FROM customers
WHERE NOT EXISTS (SELECT 1 FROM orders WHERE orders.customer_id = customers.id);

EXPLAIN (COSTS OFF)
SELECT customers.id
FROM customers
LEFT JOIN orders ON orders.customer_id = customers.id
WHERE orders.id IS NULL;
```

**You should see**, for `NOT EXISTS`: a `Nested Loop Anti Join`. An **anti join** returns the rows on one side that have **no** match on the other, and it can stop looking at the first match. Here it checks each customer against the index on `orders.customer_id`.

For the `LEFT JOIN` form, note which plan you get. Postgres 16 keeps it as a full `Hash Right Join` with `Filter: (orders.id IS NULL)` applied afterwards: it joins every customer with all of their orders, then throws almost everything away. Newer planners may recognise the pattern and turn it into an anti join. `NOT EXISTS` gets the efficient plan on every version, which is why step 2.1 recommends it.

## 6.6 Fix a bad estimate with extended statistics

**The idea.** The planner assumes that conditions on different columns are independent. If 1% of rows match condition A and 1% match condition B, it expects 1% × 1% = 0.01% to match both. When the columns are related, that assumption fails badly. In this dataset they are: `status = 'new'` is true exactly when `id % 100 = 0`.

```sql
-- pg1 psql
EXPLAIN (ANALYZE, TIMING OFF, SUMMARY OFF)
SELECT * FROM orders WHERE status = 'new' AND id % 100 = 0;
```

**You should see** the top step estimate about `rows=10` but return `actual … rows=2000`.

**What it means.** The planner multiplied about 1% (status `new`) by 0.5% (its fixed guess for an `=` test on an expression it has no statistics for, `id % 100 = 0`), giving 0.005% of 200,000 = 10 rows. Reality is 200 times higher. In a bigger query, an underestimate like that can make the planner choose a nested loop that runs once per row it expected — and then run it 2,000 times instead of 10.

Teach the planner that the two are related:

```sql
-- pg1 psql
CREATE STATISTICS IF NOT EXISTS orders_status_bucket (dependencies, mcv)
    ON status, (id % 100) FROM orders;
ANALYZE orders;
EXPLAIN (ANALYZE, TIMING OFF, SUMMARY OFF)
SELECT * FROM orders WHERE status = 'new' AND id % 100 = 0;
```

- `CREATE STATISTICS` asks `ANALYZE` to study columns **together**. `dependencies` measures how much one column determines the other; `mcv` records the most common **combinations** of values. Expressions such as `(id % 100)` are allowed since Postgres 14.
- `ANALYZE orders` collects the new statistics.

**You should see** the estimate jump to about `rows=2000`, matching reality.

**A checklist for a slow query:**

1. Run `EXPLAIN (ANALYZE, BUFFERS)` and find the lowest step where estimated and actual rows differ by 10× or more.
2. If statistics may be stale, run `ANALYZE` on the table and compare again.
3. If two filtered columns are related, add `CREATE STATISTICS`.
4. If a filter or join column has no index, add one and check that the plan uses it.
5. If a sort or hash runs out of memory, the plan shows `Sort Method: external merge` or `Batches:` above 1. Raise `work_mem` for that session.

Leave psql:

```sql
-- pg1 psql
\q
```

---

Previous: [05 — WAL and VACUUM](05-wal-and-vacuum.md) · [Back to the README](../README.md) · Next: [07 — Replication and CDC](07-replication-cdc.md)
