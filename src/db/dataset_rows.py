"""Dataset-to-row conversion helpers.

Both the production JSON loader and integration tests need to convert a parsed dataset payload
(`videos` with embedded `snapshots`) into row tuples matching the `videos` and `video_snapshots`
tables.

Keeping this conversion in one place prevents drift between loader behavior and test fixtures.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from typing import Any


def iter_video_rows(videos: Sequence[dict[str, Any]]) -> Iterable[tuple[Any, ...]]:
    """Yield row tuples for inserting into the `videos` table."""

    for video in videos:
        yield (
            str(video["id"]),
            str(video["creator_id"]),
            video["video_created_at"],
            int(video["views_count"]),
            int(video["likes_count"]),
            int(video["comments_count"]),
            int(video["reports_count"]),
            video["created_at"],
            video["updated_at"],
        )


def iter_snapshot_rows(videos: Sequence[dict[str, Any]]) -> Iterable[tuple[Any, ...]]:
    """Yield row tuples for inserting into the `video_snapshots` table."""

    for video in videos:
        for snapshot in video.get("snapshots", []):
            yield (
                str(snapshot["id"]),
                str(snapshot["video_id"]),
                int(snapshot["views_count"]),
                int(snapshot["likes_count"]),
                int(snapshot["comments_count"]),
                int(snapshot["reports_count"]),
                int(snapshot["delta_views_count"]),
                int(snapshot["delta_likes_count"]),
                int(snapshot["delta_comments_count"]),
                int(snapshot["delta_reports_count"]),
                snapshot["created_at"],
                snapshot["updated_at"],
            )

