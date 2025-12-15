"""Async Postgres connection pool.

The bot and query pipeline use an async pool (psycopg3) for efficient DB access. Every acquired
connection is configured to use UTC at the session level.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncIterator

from dotenv import load_dotenv
from psycopg import AsyncConnection
from psycopg_pool import AsyncConnectionPool

from src.db.connection import require_database_url
from src.db.session import ensure_utc


def create_pool(
        database_url: str | None = None,
        *,
        min_size: int = 1,
        max_size: int | None = None,
        timeout: float = 30.0,
) -> AsyncConnectionPool:
    """Create an async DB pool.

    Notes:
        - The returned pool is created with `open=False`. Call `await pool.open()` at startup.
        - If `database_url` is omitted, the function loads `.env` and reads `DATABASE_URL`.
    """

    if database_url is None:
        load_dotenv(".env")
        database_url = require_database_url()

    return AsyncConnectionPool(
        conninfo=database_url,
        min_size=min_size,
        max_size=max_size,
        timeout=timeout,
        open=False,
        configure=ensure_utc,
    )


@asynccontextmanager
async def get_conn(pool: AsyncConnectionPool) -> AsyncIterator[AsyncConnection]:
    """Acquire a connection from the pool with UTC session timezone enforced."""

    async with pool.connection() as conn:
        # Extra safety: enforce UTC on every acquire, even if the pool config already does it.
        await ensure_utc(conn)
        yield conn
