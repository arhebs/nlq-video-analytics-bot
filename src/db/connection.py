"""Shared Postgres connection helpers.

For deterministic date handling, every DB session must set its timezone to UTC.
"""

from __future__ import annotations

import os

import psycopg


def require_database_url() -> str:
    """Read `DATABASE_URL` from the environment or raise a clear error."""

    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        raise RuntimeError("DATABASE_URL is required (set it in .env or environment)")
    return database_url


def connect_utc(database_url: str) -> psycopg.Connection:
    """Connect to Postgres and lock the session timezone to UTC."""

    conn = psycopg.connect(database_url)
    conn.execute("SET TIME ZONE 'UTC'", prepare=False)
    return conn

