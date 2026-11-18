# 04 — Internals: MVCC

**The idea.** Many sessions read and write the same tables at the same time. If a writer had to lock a row while it changed it, every reader would have to wait. Postgres avoids this with **MVCC** (multi-version concurrency control):

- An `UPDATE` never changes a row in place. It writes a **new version** of the row and marks the old version as replaced. A `DELETE` only marks the row as deleted.
- Every transaction gets a number, its **transaction id**. Each row version records which transaction created it and which, if any, replaced or deleted it.
- When a session reads, it takes a **snapshot**: a note of which transactions had committed at that moment. It then sees exactly the row versions those committed transactions produced, and ignores the rest.

The result: readers never wait for writers, and writers never wait for readers. The cost: old row versions pile up until VACUUM cleans them (Lab 5).

In this lab you watch versions appear in hidden columns and on the raw data page, then use two sessions side by side to see what MVCC means for locking and isolation.

**Where:** psql on pg1. Steps 4.3–4.5 use two terminals.

## The hidden columns

Every table has system columns you can select by name, although `SELECT *` does not show them:

| Column | Meaning |
| --- | --- |
| `xmin` | The id of the transaction that created this row version |
| `xmax` | The id of the transaction that deleted or replaced this version; `0` if none has |
| `ctid` | Where this version physically sits in the table file, as `(page number, slot number)`. Pages are 8 KB blocks, numbered from 0; slots are numbered from 1. |

**The visibility rule, in plain words:** your snapshot sees a row version if the transaction in `xmin` had committed when your snapshot was taken, **and** the version has not been deleted from your point of view: `xmax` is 0, or belongs to a transaction that aborted, or to one that had not yet committed when your snapshot was taken.

## 4.1 Create a small table

Open **terminal A**, `cd` to `pg-lab`, and connect:

```bash
# Mac, terminal A
docker compose exec pg1 psql -U lab -d labdb
```

Wait for `pg1 labdb=#`.

```sql
-- pg1 psql, terminal A
DROP TABLE IF EXISTS accounts;
CREATE TABLE accounts (id int PRIMARY KEY, owner text, balance numeric(10,2));
INSERT INTO accounts VALUES (1, 'ana', 100.00), (2, 'ben', 50.00);
SELECT xmin, xmax, ctid, id, owner, balance FROM accounts ORDER BY id;
```

- `DROP TABLE IF EXISTS accounts` removes the table if a previous run left one; `IF EXISTS` avoids an error when it doesn't exist. On a first run psql prints `NOTICE:  table "accounts" does not exist, skipping`, which is harmless.
- `INSERT INTO accounts VALUES (…)` without a column list supplies every column in table order.
- The `SELECT` names the three hidden columns explicitly.

**You should see** something like this (your `xmin` number differs):

```
 xmin | xmax | ctid  | id | owner | balance
------+------+-------+----+-------+---------
  891 |    0 | (0,1) |  1 | ana   |  100.00
  891 |    0 | (0,2) |  2 | ben   |   50.00
```

**What it means.** Both rows have the same `xmin` because one `INSERT` (one transaction) created them. `xmax` is 0: nobody has replaced them. They sit in page 0, slots 1 and 2.

## 4.2 Watch an UPDATE create a new version

```sql
-- pg1 psql, terminal A
BEGIN;
SELECT pg_current_xact_id();
UPDATE accounts SET balance = balance + 10 WHERE id = 1;
COMMIT;
SELECT xmin, xmax, ctid, id, owner, balance FROM accounts ORDER BY id;
```

- `pg_current_xact_id()` returns the id of the transaction you are in. Inside `BEGIN … COMMIT`, it is the id that the `UPDATE` will stamp on the row.

**You should see** a number from `pg_current_xact_id()`; call it **X**. After the commit, Ana's row shows `xmin` = X, `ctid` = `(0,3)` and balance `110.00`. Ben's row is unchanged at `(0,2)`.

**What it means.** Ana's row moved from slot 1 to slot 3. The update did not overwrite slot 1; it wrote a new version in slot 3, created by transaction X. What happened to slot 1? A normal `SELECT` will never show it, but the `pageinspect` extension (included in the image) can read the raw page:

```sql
-- pg1 psql, terminal A
CREATE EXTENSION IF NOT EXISTS pageinspect;
SELECT lp, t_xmin, t_xmax, t_ctid
FROM heap_page_items(get_raw_page('accounts', 0));
```

- `CREATE EXTENSION` installs an optional add-on into the database. `pageinspect` adds functions for looking at raw storage.
- `get_raw_page('accounts', 0)` reads page 0 of the table file as raw bytes.
- `heap_page_items(…)` decodes those bytes into one row per slot. `lp` is the slot number ("line pointer"); `t_xmin`, `t_xmax`, `t_ctid` are the same values as the hidden columns, but for **every** version on the page, live or dead.

**You should see** (numbers relative to your own):

```
 lp | t_xmin | t_xmax | t_ctid
----+--------+--------+--------
  1 |    891 |      X | (0,3)
  2 |    891 |      0 | (0,2)
  3 |      X |      0 | (0,3)
```

**What it means.**

- Slot 1 is Ana's **old** version, still physically on the page. Its `t_xmax` is X (transaction X replaced it), and its `t_ctid` points forward to the new version in slot 3. Every snapshot taken after X committed skips it. It is now a **dead tuple** ("tuple" is the database word for a row version). VACUUM reclaims its space in Lab 5.
- Slot 3 is the new version: created by X, not replaced.
- The forward pointer from old to new version lets a session that was waiting on the old version find the current one (step 4.4).

Now a delete:

```sql
-- pg1 psql, terminal A
DELETE FROM accounts WHERE id = 2;
SELECT lp, t_xmin, t_xmax, t_ctid
FROM heap_page_items(get_raw_page('accounts', 0));
```

**You should see** slot 2 still on the page, now with a non-zero `t_xmax`. A `DELETE` writes no new version; it only stamps the deleting transaction's id into `xmax`. Put Ben back for the next steps:

```sql
-- pg1 psql, terminal A
INSERT INTO accounts VALUES (2, 'ben', 50.00);
```

## 4.3 Readers never wait for writers

Open a second terminal window, **terminal B**, `cd` to `pg-lab`, and connect:

```bash
# Mac, terminal B
docker compose exec pg1 psql -U lab -d labdb
```

Wait for `pg1 labdb=#`. In **terminal A**, start a transaction that changes Ana's balance and **do not commit**:

```sql
-- pg1 psql, terminal A
BEGIN;
SELECT pg_current_xact_id();
UPDATE accounts SET balance = 0 WHERE id = 1;
```

**You should see** the prompt change to `pg1 labdb=*#`. Note the transaction id; call it **Y**. Now in **terminal B**:

```sql
-- pg1 psql, terminal B
SELECT xmin, xmax, balance FROM accounts WHERE id = 1;
```

**You should see** balance `110.00` and `xmax` = **Y**.

**What it means.** Terminal A has already written a new version (balance 0) and stamped Y into the old version's `xmax`. But Y has not committed, so under the visibility rule terminal B still sees the old version, and it got its answer immediately. Readers never wait for writers. Terminal B also never sees A's uncommitted 0: Postgres never shows uncommitted data to another session.

## 4.4 Writers wait for writers

Still with terminal A's transaction open, in **terminal B**:

```sql
-- pg1 psql, terminal B
UPDATE accounts SET balance = balance + 1 WHERE id = 1;
```

**You should see** terminal B **hang**: no output, no prompt.

**What it means.** Two sessions cannot both change the same row at once. Terminal B found that the row's current version is stamped with `xmax` = Y, a transaction still in progress. It cannot know whether Y will commit (B should then update A's new version) or roll back (B should update the old one), so it waits for Y to finish.

See the wait from **terminal A**:

```sql
-- pg1 psql, terminal A
SELECT pid,
       state,
       wait_event_type,
       wait_event,
       pg_blocking_pids(pid) AS blocked_by
FROM pg_stat_activity
WHERE datname = 'labdb'
  AND pid <> pg_backend_pid();
```

- `pg_stat_activity` is a built-in view with one row per connected session. `pid` is the id of the server process serving that session.
- `pg_backend_pid()` is your own session's process id; `pid <> pg_backend_pid()` leaves yourself out.
- `pg_blocking_pids(pid)` lists the processes that session is waiting for.

**You should see** one row, for terminal B: `state` = `active`, `wait_event_type` = `Lock`, `wait_event` = `transactionid`, and `blocked_by` = `{…}` holding terminal A's process id.

**What it means.** `transactionid` says what B is waiting for: not a lock on the row itself, but for transaction Y to end. A row lock in Postgres is simply the `xmax` stamp on the row; waiters queue on the transaction that stamped it. Now release it:

```sql
-- pg1 psql, terminal A
COMMIT;
```

**You should see** terminal B wake up at once and print `UPDATE 1`. Check in **terminal B**:

```sql
-- pg1 psql, terminal B
SELECT balance FROM accounts WHERE id = 1;
```

**You should see** `1.00`.

**What it means.** After A committed, B followed the old version's forward pointer to the newest committed version (balance 0) and applied its `+ 1` to that. A's change was not lost. This re-check is how the default isolation level, READ COMMITTED, behaves.

## 4.5 REPEATABLE READ refuses an update based on stale data

**The idea.** An **isolation level** decides how much a transaction sees of other transactions' work while it runs. Under READ COMMITTED, each statement takes a fresh snapshot. Under REPEATABLE READ, the whole transaction uses one snapshot, taken at its first statement, so repeated reads always agree.

In **terminal B**:

```sql
-- pg1 psql, terminal B
BEGIN ISOLATION LEVEL REPEATABLE READ;
SELECT balance FROM accounts WHERE id = 1;
```

**You should see** `1.00`; terminal B's snapshot is now fixed. In **terminal A**, which is back in autocommit mode:

```sql
-- pg1 psql, terminal A
UPDATE accounts SET balance = 200 WHERE id = 1;
```

**You should see** `UPDATE 1`, committed immediately. Back in **terminal B**:

```sql
-- pg1 psql, terminal B
SELECT balance FROM accounts WHERE id = 1;
UPDATE accounts SET balance = balance + 1 WHERE id = 1;
```

**You should see** the `SELECT` still return `1.00`, then the `UPDATE` fail:

```
ERROR:  could not serialize access due to concurrent update
```

The prompt turns to `pg1 labdb=!#`.

**What it means.** Terminal B's snapshot still shows 1.00, but the row has meanwhile been changed to 200 by a transaction B cannot see. Applying `+ 1` to a value B never saw would silently lose A's update, so Postgres refuses. The application must roll back and retry the whole transaction; in Python this arrives as `psycopg.errors.SerializationFailure`, error code `40001`.

```sql
-- pg1 psql, terminal B
ROLLBACK;
\q
```

Close terminal B. Keep terminal A's psql open for Lab 5.

**The three isolation levels compared:**

| Level | When the snapshot is taken | If another transaction has changed a row you are updating |
| --- | --- | --- |
| READ COMMITTED (default) | At each statement | Wait for it, then apply your change to the newest version |
| REPEATABLE READ | Once, at the transaction's first statement | Wait for it, then fail with error 40001 if it committed |
| SERIALIZABLE | Once, plus tracking of what each transaction read | As REPEATABLE READ, and also fails transactions whose combined effect could not have happened one after another, even when they touched different rows |

---

Previous: [03 — Python](03-python.md) · [Back to the README](../README.md) · Next: [05 — WAL and VACUUM](05-wal-and-vacuum.md)
