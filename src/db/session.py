"""DB session configuration helpers.

The project requires deterministic date boundaries; all timestamps are treated as UTC and user "days"
are interpreted as UTC calendar days. For that to be reliable, every DB session must be locked to the
UTC timezone.
"""

from __future__ import annotations

from psycopg import AsyncConnection


async def ensure_utc(conn: AsyncConnection) -> None:
    """Ensure the current Postgres session timezone is set to UTC."""

    async with conn.cursor() as cur:
        await cur.execute("SET TIME ZONE 'UTC'", prepare=False)
    # `SET` starts a transaction when autocommit is disabled; commit so the pool doesn't see INTRANS.
    await conn.commit()
