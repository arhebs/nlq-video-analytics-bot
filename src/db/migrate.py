"""Apply SQL migrations to the configured PostgreSQL database.

This project keeps migrations as plain `.sql` files under `src/db/migrations/` and applies them in
lexicographic order. Applied migration filenames are tracked in the `schema_migrations` table.
"""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import LiteralString, cast

import psycopg
from dotenv import load_dotenv

from src.db.connection import connect_utc, require_database_url

MIGRATIONS_DIR = Path(__file__).resolve().parent / "migrations"


def _ensure_schema_migrations(conn: psycopg.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS schema_migrations
        (
            filename
            TEXT
            PRIMARY
            KEY,
            applied_at
            TIMESTAMPTZ
            NOT
            NULL
            DEFAULT
            NOW
        (
        )
            );
        """,
        prepare=False,
    )


def _list_migration_files() -> list[Path]:
    if not MIGRATIONS_DIR.exists():
        raise RuntimeError(f"Migrations directory does not exist: {MIGRATIONS_DIR}")

    files = sorted(p for p in MIGRATIONS_DIR.iterdir() if p.is_file() and p.suffix == ".sql")
    if not files:
        raise RuntimeError(f"No .sql migration files found in {MIGRATIONS_DIR}")
    return files


def _get_applied_migrations(conn: psycopg.Connection) -> set[str]:
    rows = conn.execute("SELECT filename FROM schema_migrations", prepare=False).fetchall()
    return {r[0] for r in rows}


def _apply_migration(conn: psycopg.Connection, filename: str, sql_text: str) -> None:
    with conn.transaction():
        conn.execute(cast(LiteralString, sql_text), prepare=False)
        conn.execute(
            "INSERT INTO schema_migrations(filename) VALUES (%s)",
            (filename,),
            prepare=False,
        )


def migrate(*, recreate: bool) -> None:
    """Run migrations against the database pointed to by `DATABASE_URL`."""

    load_dotenv(".env")
    database_url = require_database_url()

    files = _list_migration_files()

    with connect_utc(database_url) as conn:
        if recreate:
            conn.execute(
                """
                DROP TABLE IF EXISTS video_snapshots;
                DROP TABLE IF EXISTS videos;
                DROP TABLE IF EXISTS schema_migrations;
                """,
                prepare=False,
            )

        _ensure_schema_migrations(conn)
        applied = _get_applied_migrations(conn)

        for file_path in files:
            if file_path.name in applied:
                continue

            sql_text = file_path.read_text(encoding="utf-8")
            _apply_migration(conn, file_path.name, sql_text)


def main() -> None:
    """CLI entry point for applying migrations."""

    parser = argparse.ArgumentParser(description="Apply SQL migrations to Postgres.")
    parser.add_argument(
        "--recreate",
        action="store_true",
        help="Drop existing tables and re-apply all migrations (destructive).",
    )
    args = parser.parse_args()

    migrate(recreate=args.recreate)


if __name__ == "__main__":
    main()
