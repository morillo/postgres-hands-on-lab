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
