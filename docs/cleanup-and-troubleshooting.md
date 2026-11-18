# Cleanup and troubleshooting

## Cleanup

**The idea.** Remove things in reverse order of dependency. A subscription owns a slot on pg1, so drop the subscription first: that also removes its slot. Then remove the publication and the lab-only tables, and finally the containers.

**1. On pg2, drop the subscription** (terminal B):

```sql
-- pg2 psql, terminal B
DROP SUBSCRIPTION shop_sub;
\q
```

**You should see** `NOTICE:  dropped replication slot "shop_sub" on publisher`, then `DROP SUBSCRIPTION`.

**2. On pg1, drop the publication and the lab-only tables** (terminal A):

```sql
-- pg1 psql, terminal A
DROP PUBLICATION shop_pub;
SELECT slot_name FROM pg_replication_slots;
DROP TABLE IF EXISTS events, bloat, accounts;
\q
```

**You should see** `DROP PUBLICATION`; then `(0 rows)`, confirming no slot is left holding WAL; then `DROP TABLE`. The `events`, `bloat` and `accounts` tables came from Labs 3, 5 and 4.

**3. Stop the containers** (Mac terminal, in `pg-lab`). Choose one:

```bash
# Mac: stop and remove the containers, KEEP the data
docker compose down
```

```bash
# Mac: stop and remove the containers AND delete all data
docker compose down -v
```

- `docker compose down` removes the containers but keeps the named volumes `pg1-data` and `pg2-data`. A later `docker compose up -d --wait` brings both databases back with all their data.
- `-v` also deletes the volumes. The next `up` starts from empty databases, and you would begin again at Lab 1.

**4. Optional.** Delete the downloaded image (about 150 MB on disk):

```bash
# Mac
docker image rm postgres:17
```

To remove the project itself, step out of it and check where you are:

```bash
# Mac
cd ..
pwd
```

`pwd` must show the folder that contains `pg-lab`. Then delete the folder in Finder, or with the command below. `rm -rf` deletes without asking and cannot be undone.

```bash
# Mac
rm -rf pg-lab
```

## Troubleshooting

| Symptom | Cause | Fix |
| --- | --- | --- |
| `zsh: command not found: psql` | You typed psql in the Mac terminal. psql runs inside the containers. | Use `docker compose exec pg1 psql -U lab -d labdb` |
| `ERROR:  syntax error at or near "docker"` | You typed a Mac command at a psql prompt | `\q` first, then run it in the Mac terminal |
| Prompt shows `-#` instead of `=#` and nothing runs | psql is waiting for the end of a statement | Type `;` and press Enter, or Ctrl-C to discard |
| Prompt shows `=!#` and every statement fails with `current transaction is aborted` | An earlier statement in this transaction failed | `ROLLBACK;` |
| `docker compose up` fails with `port is already allocated` | Another program already uses Mac port 55432 or 55433 | Change the left-hand number in `ports:` in `compose.yaml`, for example `"55532:5432"`, and use the new port in `PG_DSN` and `SA_URL` in `.env` |
| A container never becomes healthy | The server failed to start | `docker compose logs pg1` shows why |
| `no configuration file provided: not found` | You ran `docker compose` outside the `pg-lab` folder | `cd` into `pg-lab` |
| Python: `connection refused` | The containers are not running | `docker compose up -d --wait` |
| Python: `password authentication failed` | Wrong user or password in `PG_DSN` or `SA_URL` | Both are `lab`, as set in `.env`. A password changed in `.env` after the first `docker compose up` does not reach the existing database; the volume keeps the old one until `docker compose down -v` |
| Python: `PG_DSN is not set` (or `SA_URL`) | The script ran without `.env` loaded | `cp .env.example .env` if `.env` is missing, and run scripts as `uv run --env-file .env python py/<script>.py` |
| `required variable POSTGRES_USER is missing a value` | `docker compose` found no `.env` in the project folder | `cp .env.example .env` (step 0.1) |
| `relation "orders" does not exist` | Connected to the wrong container or database, or the tables were never created | Check the prompt says `pg1 labdb`; on pg2 the tables exist only after step 7.4 |
| Lab results don't match the doc | The data was changed by an earlier lab | Re-run the seed: `docker compose exec pg1 psql -U lab -d labdb -f /sql/seed.sql` |
| `cannot drop table … because other objects depend on it`, or `TRUNCATE` hangs | A subscription or open transaction still uses the table | Finish or roll back other sessions; in Lab 7, check `pg_stat_activity` and `pg_replication_slots` |
| pg1's disk use keeps growing | A replication slot whose consumer is gone is holding WAL (step 7.3) | `SELECT slot_name, active FROM pg_replication_slots;` then drop the unused one with `SELECT pg_drop_replication_slot('name');` |

---

Previous: [08 — How it fits together](08-how-it-fits-together.md) · [Back to the README](../README.md)
