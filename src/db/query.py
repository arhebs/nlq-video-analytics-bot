"""Safe DB query helpers.

These helpers are used by the bot pipeline. They never interpolate user values into SQL and always
return a plain integer value to satisfy the bot output contract.
"""

from __future__ import annotations

from typing import Any, LiteralString, cast

from psycopg import AsyncConnection


async def fetch_scalar_int(conn: AsyncConnection, sql: str, params: tuple[Any, ...] = ()) -> int:
    """Execute a scalar query and return an `int`.

    Contract:
        - Returns `0` if the query yields no rows or the first column is NULL.
        - The query must be parameterized; all values are passed via `params`.
        - DB errors are not swallowed (caller decides how to handle them).
    """

    async with conn.cursor() as cur:
        await cur.execute(cast(LiteralString, sql), params)
        row = await cur.fetchone()

    if not row:
        return 0

    value = row[0]
    if value is None:
        return 0

    return int(value)

