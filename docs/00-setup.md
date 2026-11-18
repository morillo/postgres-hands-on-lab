# 00 — Setup

**The idea.** You need a database server to practise on. Instead of installing Postgres on your Mac, you run it in Docker containers: isolated, disposable, and identical every time. You start two of them. **pg1** is the main database for every lab. **pg2** sits idle until Lab 7, where it becomes a live copy of pg1. Every file the labs use lives in one project folder, `pg-lab/`, which is a clone of this repository.

## How every step is laid out

Each step follows the same four parts:

1. **The idea.** What the step is about and why it matters, in plain words.
2. **The code.** Written to be read: full names, no shortcuts.
3. **Line by line.** What each line does. Every symbol, operator and function is explained the first time it appears.
4. **What you should see, and what it means.**

## Prerequisites

- **Docker Desktop**, running.
- **uv**, the Python project manager.
- **Git**, to clone the repository.
- Nothing else. The `psql` command-line client runs inside the containers, so you install no Postgres software on your Mac.

Check all three in the Mac terminal:

```bash
# Mac
docker compose version
uv --version
git --version
```

**You should see** `Docker Compose version v2.` (or later) followed by a version number, then a `uv` version and a `git` version. A `command not found` means that tool is missing.

## Where each command runs

You will type into three different places. Pasting a command into the wrong place is the most common mistake, so every step opens with a **Where:** line, and every code block starts with a comment naming its place: `# Mac` for the terminal, `-- pg1 psql` for the database.

| Place | What the prompt looks like | How to get there | How to leave |
| --- | --- | --- | --- |
| Mac terminal, inside the `pg-lab` folder | `%` | Open Terminal and `cd` into `pg-lab` | — |
| psql connected to **pg1** (the main database) | `pg1 labdb=#` | `docker compose exec pg1 psql -U lab -d labdb` | Type `\q` |
| psql connected to **pg2** (the copy, used only in Lab 7) | `pg2 labdb=#` | `docker compose exec pg2 psql -U lab -d labdb` | Type `\q` |

What goes wrong in the wrong place:

- Typing `psql` in the Mac terminal gives `zsh: command not found: psql`. That is expected; psql lives in the containers.
- Typing a `docker …` command at a psql prompt gives `ERROR:  syntax error at or near "docker"`, because psql tries to run it as SQL.

Python scripts (Lab 3) run in the Mac terminal and talk to the database over the network. Labs 4, 5 and 7 need two terminal windows open at once; the doc calls them **terminal A** and **terminal B**.

## Reading psql output

- psql waits for a semicolon `;` before it runs a statement. If the prompt changes from `pg1 labdb=#` to `pg1 labdb-#`, psql is waiting for the rest of a statement. Type `;` and press Enter to run it, or press Ctrl-C to throw it away.
- After a successful command psql prints a short tag: `INSERT 0 3` means "inserted 3 rows" (the `0` is a leftover field that is always 0). `UPDATE 1` and `DELETE 1` mean one row changed.

**Where:** Mac terminal.

## 0.1 Clone the repository

**The idea.** Every file the labs use is already in the repository: the Compose file, the psql prompt files, the SQL scripts and the Python scripts. You clone it into a folder named `pg-lab`, then create the one file that is not in git, `.env`, which holds the database user and password.

First `cd` into the folder where you keep your projects (not your home folder itself). Then:

```bash
# Mac
git clone https://github.com/morillo/postgres-hands-on-lab.git pg-lab
cd pg-lab
cp .env.example .env
pwd
```

Line by line:

1. `git clone <address> pg-lab` downloads the repository into a new folder named `pg-lab`. This doc calls the folder `pg-lab` throughout.
2. `cd pg-lab` moves into the project folder.
3. `cp .env.example .env` copies the example settings into `.env`. `cp` prints nothing on success. `.env` is listed in `.gitignore`, so your copy, and any password you change in it, never ends up in git.
4. `pwd` ("print working directory") shows where you are.

**You should see** git's `Cloning into 'pg-lab'...` progress lines, then a path ending in `/pg-lab`. Every Mac command in this doc assumes you are in this folder. If you open a new terminal window, `cd` back here first.

What the folder holds:

| Path | What it is | Used in |
| --- | --- | --- |
| `compose.yaml` | The two database containers | Step 0.2 |
| `psqlrc/pg1`, `psqlrc/pg2` | Settings files that give each psql its own prompt | Step 0.3 |
| `sql/schema.sql`, `sql/seed.sql` | The shop tables and the script that fills them | Lab 1 |
| `py/` | The Python scripts | Lab 3 |
| `pyproject.toml`, `uv.lock`, `.python-version` | The Python project and its pinned packages | Lab 3 |
| `.env.example` | The lab's settings; you copied it to `.env` | Steps 0.2 and 3.1 |
| `tests/` | Automated checks that the scripts print what this doc says | Not needed for the labs |

`.env` holds:

```bash
# Lab settings. Copy this file to .env (git-ignored): cp .env.example .env
# Docker Compose reads .env automatically; the Python scripts get it through
# `uv run --env-file .env`.

# Database user, password and database created on the containers' first start
POSTGRES_USER=lab
POSTGRES_PASSWORD=lab
POSTGRES_DB=labdb

# Connection addresses for the Python scripts (pg1, Mac port 55432)
PG_DSN=postgresql://lab:lab@localhost:55432/labdb
SA_URL=postgresql+psycopg://lab:lab@localhost:55432/labdb
```

- Each line is `NAME=value`; lines starting with `#` are comments.
- `POSTGRES_USER`, `POSTGRES_PASSWORD` and `POSTGRES_DB` are read by Docker Compose, which loads a file named `.env` from the project folder automatically (step 0.2).
- `PG_DSN` and `SA_URL` are the connection addresses the Python scripts use (Lab 3). They repeat the user `lab` and password `lab`; if you change the password, change it in all three places.

## 0.2 Describe the two databases in a Compose file

**The idea.** Docker Compose reads one file, `compose.yaml`, that lists the containers you want and how each is configured. One command then starts or stops all of them together.

The file is already in the repository. Print it:

```bash
# Mac
cat compose.yaml
```

**You should see** the file:

```yaml
name: pg-lab

services:
  pg1:
    image: postgres:17
    environment:
      POSTGRES_USER: ${POSTGRES_USER:?copy .env.example to .env first}
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD:?copy .env.example to .env first}
      POSTGRES_DB: ${POSTGRES_DB:?copy .env.example to .env first}
    command:
      - postgres
      - -c
      - wal_level=logical
      - -c
      - max_replication_slots=10
      - -c
      - max_wal_senders=10
    ports:
      - "55432:5432"
    volumes:
      - pg1-data:/var/lib/postgresql/data
      - ./psqlrc/pg1:/root/.psqlrc:ro
      - ./sql:/sql:ro
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -h localhost -U $${POSTGRES_USER} -d $${POSTGRES_DB}"]
      interval: 2s
      timeout: 3s
      retries: 30

  pg2:
    image: postgres:17
    environment:
      POSTGRES_USER: ${POSTGRES_USER:?copy .env.example to .env first}
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD:?copy .env.example to .env first}
      POSTGRES_DB: ${POSTGRES_DB:?copy .env.example to .env first}
    ports:
      - "55433:5432"
    volumes:
      - pg2-data:/var/lib/postgresql/data
      - ./psqlrc/pg2:/root/.psqlrc:ro
      - ./sql:/sql:ro
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -h localhost -U $${POSTGRES_USER} -d $${POSTGRES_DB}"]
      interval: 2s
      timeout: 3s
      retries: 30

volumes:
  pg1-data:
  pg2-data:
```

**What the file says, piece by piece:**

| Part | Meaning |
| --- | --- |
| `name: pg-lab` | The project name. Compose puts it at the start of every container name (step 0.4), so the names match this doc whatever you called the folder. |
| `services:` | The list of containers. There are two, named `pg1` and `pg2`. These names are also how the containers find each other on Docker's private network (Lab 7). |
| `image: postgres:17` | Use the official PostgreSQL image, major version 17. Pinning the version matters: the version 18 image stores its data in a different folder, so an unpinned image would break the data path below. |
| `environment:` | Settings the image reads on its very first start. `${POSTGRES_USER:?…}` means: use the value of `POSTGRES_USER` from `.env`, and if it is missing, stop with the message after `:?`. With the values from `.env.example` they create a user `lab` with password `lab`, and an empty database `labdb` owned by that user. The `lab` user is a superuser: allowed to do anything. |
| `command:` (pg1 only) | The command that starts the server, with extra settings. Each `-c` is followed by one `setting=value`. In YAML, each ` -  ` line is one item of a list, so this reads `postgres -c wal_level=logical -c max_replication_slots=10 -c max_wal_senders=10`. |
| `wal_level=logical` | Makes the write-ahead log (Lab 5) detailed enough to reconstruct row changes, which Lab 7 needs. The default level, `replica`, is not enough. Changing it later requires a restart. |
| `max_replication_slots=10`, `max_wal_senders=10` | Room for the replication connections Lab 7 creates. |
| `ports: "55432:5432"` | `Mac port : container port`. Inside the container Postgres listens on its standard port 5432; your Mac reaches it on port 55432. The unusual Mac port avoids a clash with any Postgres already running on your Mac. pg2 uses 55433. |
| `pg1-data:/var/lib/postgresql/data` | Stores the database files in a Docker volume named `pg1-data`. The data survives stopping and restarting the container. |
| `./psqlrc/pg1:/root/.psqlrc:ro` | Makes your Mac file `psqlrc/pg1` appear inside the container as `/root/.psqlrc`, the file psql reads when it starts. `ro` means read-only. Step 0.3 explains what goes in it. |
| `./sql:/sql:ro` | Makes your Mac folder `sql/` appear inside the container as `/sql`, so psql can run the SQL scripts that live on the Mac. |
| `healthcheck:` | Every 2 seconds, Docker runs `pg_isready`, a small tool that asks "is the server accepting connections?". The container counts as healthy once it answers yes. `-h localhost` makes the check go over the network rather than a local file socket; during its first start the image runs a temporary server that only listens on the file socket, and checking over the network avoids reporting healthy too early. `$${POSTGRES_USER}` has a doubled `$`, so Compose leaves it alone and the shell inside the container fills in the container's own `POSTGRES_USER`. |
| `volumes:` at the bottom | Declares the two named volumes used above. |

## 0.3 Give each database its own psql prompt

**The idea.** The psql prompt normally shows only the database name, and both containers have a database called `labdb`. In Lab 7 you will have both open side by side. A prompt that starts with `pg1` or `pg2` tells you at a glance which one you are typing into.

The two files are already in the repository. `psqlrc/pg2` is the same with `pg2` in place of `pg1`. Print pg1's:

```bash
# Mac
cat psqlrc/pg1
```

Line by line:

- `\set PROMPT1 '…'` is a psql command (psql commands start with a backslash and are not SQL). It sets the normal prompt.
- `PROMPT2` is the prompt psql shows while you are in the middle of a statement that has no `;` yet.
- Inside the quotes, psql replaces each `%` code with live information:

| Code | Replaced with | Example |
| --- | --- | --- |
| `%/` | The database you are connected to | `labdb` |
| `%R` | `=` normally; `-` while a statement is unfinished | `=` |
| `%x` | Nothing normally; `*` inside an open transaction; `!` inside a transaction that hit an error | `*` |
| `%#` | `#` when you are a superuser, `>` otherwise | `#` |

So the prompt reads `pg1 labdb=#` normally, `pg1 labdb=*#` after you start a transaction (Lab 1), and `pg1 labdb=!#` after an error inside one.

**You should see:**

```
\set PROMPT1 'pg1 %/%R%x%# '
\set PROMPT2 'pg1 %/%R%x%# '
```

## 0.4 Start both databases

```bash
# Mac
docker compose up -d --wait
```

- `docker compose up` creates and starts every service in `compose.yaml`.
- `-d` ("detached") runs them in the background and gives you your terminal back.
- `--wait` makes the command wait until both healthchecks pass, so when it returns, the databases are ready.

The first run downloads the `postgres:17` image, about 150 MB. **You should see**, at the end (exact wording varies with your Compose version):

```
 ✔ Container pg-lab-pg1-1  Healthy
 ✔ Container pg-lab-pg2-1  Healthy
```

Compose names each container `<folder>-<service>-<number>`, hence `pg-lab-pg1-1`. Confirm with:

```bash
# Mac
docker compose ps
```

**You should see** two lines, `pg1` and `pg2`, each with a status of `Up … (healthy)`. Their port columns show `0.0.0.0:55432->5432/tcp` and `0.0.0.0:55433->5432/tcp`: Mac port on the left, container port on the right.

## 0.5 Connect with psql

```bash
# Mac
docker compose exec pg1 psql -U lab -d labdb
```

- `docker compose exec pg1` runs a command inside the running `pg1` container.
- `psql` is the command it runs: PostgreSQL's interactive client.
- `-U lab` connects as user `lab`; `-d labdb` connects to database `labdb`.

No password is asked for. psql runs inside the same container as the server and connects through a local file (a Unix socket), and the image trusts local connections. Python in Lab 3 connects from outside the container, over the network, and must give the password.

Wait for the `pg1 labdb=#` prompt, then run:

```sql
-- pg1 psql
SELECT version();
SHOW wal_level;
\conninfo
```

- `SELECT version();` calls the built-in function `version()`, which returns the server's version text.
- `SHOW wal_level;` displays the current value of one server setting.
- `\conninfo` (a psql command) describes your current connection.

**You should see** a version string starting with `PostgreSQL 17.`, then `wal_level` showing `logical` (the setting from the Compose file took effect), then:

```
You are connected to database "labdb" as user "lab" via socket in "/var/run/postgresql" at port "5432".
```

psql commands you will use throughout:

| Command | What it does |
| --- | --- |
| `\dt` | Lists the tables in the database |
| `\d orders` | Describes one table: its columns, indexes and constraints |
| `\di` | Lists the indexes |
| `\x auto` | Prints wide rows vertically, one column per line, when they don't fit the screen |
| `\i /sql/seed.sql` | Runs the SQL in a file. `/sql` is your Mac's `sql/` folder, mounted in step 0.2. |
| `\q` | Quits psql and returns you to the Mac terminal |

Stay in this psql session for Lab 1.

---

[Back to the README](../README.md) · Next: [01 — SQL basics](01-sql-basics.md)
