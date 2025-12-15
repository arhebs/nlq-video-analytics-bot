"""Load the provided `videos.json` dataset into Postgres.

The dataset is expected to be a JSON object with a single top-level key `"videos"` containing a list
of video objects. Each video includes final counters and an embedded `"snapshots"` list.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Iterable
from urllib.request import urlopen

from dotenv import load_dotenv

from src.db.connection import connect_utc, require_database_url


def _load_json_bytes(*, path: str | None, url: str | None) -> bytes:
    if bool(path) == bool(url):
        raise ValueError("Exactly one of --path or --url must be provided")

    if path:
        return Path(path).read_bytes()

    assert url is not None
    with urlopen(url) as resp:  # noqa: S310 (controlled URL from CLI)
        return resp.read()


def _iter_video_rows(videos: list[dict]) -> Iterable[tuple]:
    for v in videos:
        yield (
            str(v["id"]),
            str(v["creator_id"]),
            v["video_created_at"],
            int(v["views_count"]),
            int(v["likes_count"]),
            int(v["comments_count"]),
            int(v["reports_count"]),
            v["created_at"],
            v["updated_at"],
        )


def _iter_snapshot_rows(videos: list[dict]) -> Iterable[tuple]:
    for v in videos:
        for s in v.get("snapshots", []):
            yield (
                str(s["id"]),
                str(s["video_id"]),
                int(s["views_count"]),
                int(s["likes_count"]),
                int(s["comments_count"]),
                int(s["reports_count"]),
                int(s["delta_views_count"]),
                int(s["delta_likes_count"]),
                int(s["delta_comments_count"]),
                int(s["delta_reports_count"]),
                s["created_at"],
                s["updated_at"],
            )


def _chunks(iterable: Iterable[tuple], size: int) -> Iterable[list[tuple]]:
    chunk: list[tuple] = []
    for item in iterable:
        chunk.append(item)
        if len(chunk) >= size:
            yield chunk
            chunk = []
    if chunk:
        yield chunk


def load_dataset(*, path: str | None, url: str | None, truncate: bool, batch_size: int) -> None:
    """Load the dataset into `videos` and `video_snapshots` tables."""

    if batch_size <= 0:
        raise ValueError("--batch-size must be a positive integer")

    load_dotenv(".env")
    database_url = require_database_url()

    payload_bytes = _load_json_bytes(path=path, url=url)
    payload = json.loads(payload_bytes)

    if not isinstance(payload, dict) or "videos" not in payload or not isinstance(payload["videos"], list):
        raise ValueError("Unexpected dataset format: expected object with key 'videos' containing a list")

    videos: list[dict] = payload["videos"]

    with connect_utc(database_url) as conn:
        with conn.transaction():
            with conn.cursor() as cur:
                if truncate:
                    cur.execute("TRUNCATE video_snapshots, videos", prepare=False)

                cur.executemany(
                    """
                    INSERT INTO videos (
                        id, creator_id, video_created_at,
                        views_count, likes_count, comments_count, reports_count,
                        created_at, updated_at
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (id) DO UPDATE SET
                        creator_id = EXCLUDED.creator_id,
                        video_created_at = EXCLUDED.video_created_at,
                        views_count = EXCLUDED.views_count,
                        likes_count = EXCLUDED.likes_count,
                        comments_count = EXCLUDED.comments_count,
                        reports_count = EXCLUDED.reports_count,
                        created_at = EXCLUDED.created_at,
                        updated_at = EXCLUDED.updated_at
                    """,
                    list(_iter_video_rows(videos)),
                )

                for snapshot_batch in _chunks(_iter_snapshot_rows(videos), batch_size):
                    cur.executemany(
                        """
                        INSERT INTO video_snapshots (
                            id, video_id,
                            views_count, likes_count, comments_count, reports_count,
                            delta_views_count, delta_likes_count, delta_comments_count, delta_reports_count,
                            created_at, updated_at
                        )
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                        ON CONFLICT (id) DO UPDATE SET
                            video_id = EXCLUDED.video_id,
                            views_count = EXCLUDED.views_count,
                            likes_count = EXCLUDED.likes_count,
                            comments_count = EXCLUDED.comments_count,
                            reports_count = EXCLUDED.reports_count,
                            delta_views_count = EXCLUDED.delta_views_count,
                            delta_likes_count = EXCLUDED.delta_likes_count,
                            delta_comments_count = EXCLUDED.delta_comments_count,
                            delta_reports_count = EXCLUDED.delta_reports_count,
                            created_at = EXCLUDED.created_at,
                            updated_at = EXCLUDED.updated_at
                        """,
                        snapshot_batch,
                    )


def main() -> None:
    """CLI entry point for loading the dataset into Postgres."""

    parser = argparse.ArgumentParser(description="Load the provided videos dataset into Postgres.")
    src = parser.add_mutually_exclusive_group(required=True)
    src.add_argument("--path", help="Path to the dataset JSON file (e.g. videos.json).")
    src.add_argument("--url", help="URL to download the dataset JSON.")
    parser.add_argument(
        "--truncate",
        action="store_true",
        help="TRUNCATE target tables before loading (destructive).",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=1_000,
        help="Number of snapshot rows per insert batch.",
    )
    args = parser.parse_args()

    load_dataset(
        path=args.path,
        url=args.url,
        truncate=args.truncate,
        batch_size=args.batch_size,
    )


if __name__ == "__main__":
    main()
