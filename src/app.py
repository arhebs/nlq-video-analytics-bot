"""Application composition root.

This module wires together configuration, DB pool, and parser settings for the bot runtime.
"""

from __future__ import annotations

from dataclasses import dataclass

from psycopg_pool import AsyncConnectionPool

from src.config.settings import Settings
from src.db.pool import create_pool


@dataclass(frozen=True)
class App:
    """Shared application dependencies for handlers."""

    settings: Settings
    pool: AsyncConnectionPool


def create_app(settings: Settings) -> App:
    """Create the application container.

    Note:
        The returned DB pool is not opened. Call `await app.pool.open()` at startup.
    """

    pool = create_pool(settings.database_url, max_size=10)
    return App(settings=settings, pool=pool)

