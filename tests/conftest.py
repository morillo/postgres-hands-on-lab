"""Shared fixtures: a freshly seeded lab database and a helper to run the lab scripts.

The tests need a running PostgreSQL 17 server reachable at PG_DSN: pg1 from
compose.yaml locally, a postgres:17 service container in CI. They drop and
re-create the four shop tables, so any lab data in that database is replaced.
"""

import subprocess
import sys
from pathlib import Path

import psycopg
import pytest

from settings import pg_dsn

REPO_ROOT = Path(__file__).resolve().parent.parent
SQL_DIR = REPO_ROOT / "sql"
SCRIPTS_DIR = REPO_ROOT / "py"


def sql_without_psql_commands(path: Path) -> bytes:
    """Read a SQL file and drop psql meta-commands, the lines that start with a backslash.

    psql understands those lines; the server does not, and psycopg sends the
    file straight to the server.

    Args:
        path: The SQL file to read.

    Returns:
        The file's SQL, ready to send with psycopg.
    """
    kept_lines: list[str] = []
    for line in path.read_text().splitlines():
        if not line.startswith("\\"):
            kept_lines.append(line)
    return "\n".join(kept_lines).encode()


@pytest.fixture(scope="session")
def seeded_database() -> str:
    """Create the Lab 1 schema and load sql/seed.sql, once per test session.

    Returns:
        The connection address of the seeded database.
    """
    dsn = pg_dsn()
    with psycopg.connect(dsn, autocommit=True) as conn:
        conn.execute("DROP TABLE IF EXISTS order_items, orders, products, customers, events")
        conn.execute(sql_without_psql_commands(SQL_DIR / "schema.sql"))
        conn.execute(sql_without_psql_commands(SQL_DIR / "seed.sql"))
    return dsn


def run_script(script_name: str, working_dir: Path) -> list[str]:
    """Run one lab script the way the docs do and return its output lines.

    Args:
        script_name: File name inside py/, for example "01_basics.py".
        working_dir: Folder to run in; 03_bulk.py writes its CSV below it.

    Returns:
        The script's standard output, split into lines.
    """
    completed = subprocess.run(
        [sys.executable, str(SCRIPTS_DIR / script_name)],
        cwd=working_dir,
        capture_output=True,
        text=True,
        check=False,
        timeout=300,
    )
    assert completed.returncode == 0, completed.stderr
    return completed.stdout.splitlines()
