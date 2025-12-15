"""Integration tests against a real Postgres database.

These tests exercise the end-to-end pipeline:
rules parser -> deterministic SQL builder -> psycopg async pool -> scalar result.

They are skipped if `DATABASE_URL` is not configured or the DB is unreachable.
"""

from __future__ import annotations

import json
import os
import uuid
from collections.abc import AsyncIterator, Iterator
from pathlib import Path
from typing import Any, LiteralString, NoReturn, cast

import psycopg
import pytest
from dotenv import load_dotenv
from psycopg import sql
from psycopg_pool import AsyncConnectionPool

from src.db.connection import connect_utc
from src.db.dataset_rows import iter_snapshot_rows, iter_video_rows
from src.db.pool import create_pool, get_conn
from src.db.query import fetch_scalar_int
from src.intent.parser import parse_intent_with_source
from src.sql.builder import build_query

_FIXTURE_PATH = Path(__file__).resolve().parent / "fixtures" / "videos_fixture.json"


def _skip(reason: str) -> NoReturn:
    pytest.skip(reason)


def _require_database_url() -> str:
    load_dotenv(".env")
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        _skip("DATABASE_URL is not set; skipping integration tests")
    return database_url


@pytest.fixture(scope="session")
def prepared_schema() -> Iterator[str]:
    """Create an isolated schema, run migrations, and load a tiny fixture dataset."""

    database_url = _require_database_url()
    schema = f"it_{uuid.uuid4().hex}"

    payload = json.loads(_FIXTURE_PATH.read_text(encoding="utf-8"))
    videos: list[dict[str, Any]] = payload["videos"]

    try:
        conn_ctx = connect_utc(database_url)
    except psycopg.OperationalError as exc:
        _skip(f"Postgres is unreachable ({exc}); skipping integration tests")

    with conn_ctx as conn:
        with conn.transaction():
            conn.execute(
                sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(schema)),
                prepare=False,
            )
            conn.execute(
                sql.SQL("SET search_path TO {}").format(sql.Identifier(schema)),
                prepare=False,
            )

            for migration_name in ("001_create_tables.sql", "002_create_indexes.sql"):
                sql_text = (
                        Path(__file__).resolve().parents[1]
                        / "src"
                        / "db"
                        / "migrations"
                        / migration_name
                ).read_text(encoding="utf-8")
                conn.execute(cast(LiteralString, sql_text), prepare=False)

            video_rows = list(iter_video_rows(videos))
            snapshot_rows = list(iter_snapshot_rows(videos))

            with conn.cursor() as cur:
                cur.executemany(
                    """
                    INSERT INTO videos (id,
                                        creator_id,
                                        video_created_at,
                                        views_count,
                                        likes_count,
                                        comments_count,
                                        reports_count,
                                        created_at,
                                        updated_at)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    video_rows,
                )
                cur.executemany(
                    """
                    INSERT INTO video_snapshots (id,
                                                 video_id,
                                                 views_count,
                                                 likes_count,
                                                 comments_count,
                                                 reports_count,
                                                 delta_views_count,
                                                 delta_likes_count,
                                                 delta_comments_count,
                                                 delta_reports_count,
                                                 created_at,
                                                 updated_at)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    snapshot_rows,
                )

    yield schema

    # noinspection PyBroadException
    try:
        with psycopg.connect(database_url) as conn:
            with conn.transaction():
                conn.execute(
                    sql.SQL("DROP SCHEMA IF EXISTS {} CASCADE").format(sql.Identifier(schema)),
                    prepare=False,
                )
    except Exception:
        # Cleanup best-effort: do not fail test run on teardown.
        pass


@pytest.fixture(scope="session")
async def pool() -> AsyncIterator[AsyncConnectionPool]:
    """Create an async connection pool for integration tests."""

    database_url = _require_database_url()
    db_pool = create_pool(database_url, max_size=2)
    try:
        await db_pool.open(wait=True)
    except Exception as exc:
        _skip(f"Postgres is unreachable ({exc}); skipping integration tests")
    yield db_pool
    await db_pool.close()


async def _fetch_in_schema(pool: Any, schema: str, query_sql: str, params: tuple[Any, ...]) -> int:
    async with get_conn(pool) as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                sql.SQL("SET search_path TO {}").format(sql.Identifier(schema)),
                prepare=False,
            )
        await conn.commit()
        value = await fetch_scalar_int(conn, query_sql, params)
        await conn.commit()
        return value


@pytest.mark.asyncio
async def test_pool_enforces_utc_timezone(pool: Any, prepared_schema: str) -> None:
    async with get_conn(pool) as conn:
        async with conn.cursor() as cur:
            await cur.execute(f"SET search_path TO {prepared_schema}", prepare=False)
            await cur.execute("SHOW TimeZone", prepare=False)
            row = await cur.fetchone()
        assert row is not None
        assert row[0] == "UTC"


@pytest.mark.asyncio
async def test_example_queries_end_to_end(pool: Any, prepared_schema: str) -> None:
    cases = [
        ("Сколько всего видео есть в системе?", 3),
        (
            "Сколько видео у креатора с id c01 вышло с 1 по 5 ноября 2025 включительно?",
            1,
        ),
        ("Сколько видео набрало больше 100 000 просмотров за всё время?", 2),
        ("На сколько просмотров в сумме выросли все видео 28 ноября 2025?", 18),
        ("Сколько разных видео получали новые просмотры 27 ноября 2025?", 2),
        (
            "Сколько всего есть замеров статистики (по всем видео), "
            "в которых число просмотров за час оказалось отрицательным?",
            1,
        ),
    ]

    for text, expected in cases:
        parse_result = parse_intent_with_source(text, llm_enabled=False)
        query_sql, params = build_query(parse_result.intent)
        got = await _fetch_in_schema(pool, prepared_schema, query_sql, params)
        assert got == expected
