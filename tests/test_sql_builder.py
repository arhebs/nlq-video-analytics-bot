"""Tests for deterministic SQL builder (allowlists + parameter binding)."""

from __future__ import annotations

from datetime import date, time

from src.intent.schema import (
    DateRange,
    DateRangeScope,
    Filters,
    Intent,
    Metric,
    Operation,
    Threshold,
    ThresholdAppliesTo,
    TimeWindow,
)
from src.sql.builder import build_query


def _placeholder_count(sql: str) -> int:
    return sql.count("%s")


def test_build_count_videos_no_filters() -> None:
    sql, params = build_query(Intent(operation=Operation.count_videos, metric=None))
    assert "SELECT COUNT(*)::bigint" in sql
    assert "FROM videos v" in sql
    assert "WHERE" not in sql
    assert params == ()
    assert _placeholder_count(sql) == 0


def test_build_count_videos_creator_and_date_range() -> None:
    intent = Intent(
        operation=Operation.count_videos,
        metric=None,
        date_range=DateRange(
            scope=DateRangeScope.videos_published_at,
            start_date=date(2025, 11, 1),
            end_date=date(2025, 11, 5),
            inclusive=True,
        ),
        filters=Filters(creator_id="aca1061a9d324ecf8c3fa2bb32d7be63"),
    )
    sql, params = build_query(intent)

    assert "v.creator_id = %s" in sql
    assert "v.video_created_at >= %s AND v.video_created_at < %s" in sql
    assert "aca1061a9d324ecf8c3fa2bb32d7be63" not in sql
    assert params[0] == "aca1061a9d324ecf8c3fa2bb32d7be63"
    assert params[1].isoformat() == "2025-11-01T00:00:00+00:00"
    assert params[2].isoformat() == "2025-11-06T00:00:00+00:00"
    assert _placeholder_count(sql) == len(params)


def test_build_sum_total_metric_over_videos() -> None:
    intent = Intent(
        operation=Operation.sum_total_metric,
        metric=Metric.views,
        date_range=DateRange(
            scope=DateRangeScope.videos_published_at,
            start_date=date(2025, 6, 1),
            end_date=date(2025, 6, 30),
            inclusive=True,
        ),
        filters=Filters(),
    )
    sql, params = build_query(intent)

    assert "SELECT COALESCE(SUM(v.views_count), 0)::bigint" in sql
    assert "FROM videos v" in sql
    assert "v.video_created_at >= %s AND v.video_created_at < %s" in sql
    assert params[0].isoformat() == "2025-06-01T00:00:00+00:00"
    assert params[1].isoformat() == "2025-07-01T00:00:00+00:00"
    assert _placeholder_count(sql) == len(params)


def test_build_count_videos_final_total_threshold_is_parameterized() -> None:
    intent = Intent(
        operation=Operation.count_videos,
        metric=None,
        filters=Filters(
            thresholds=[
                Threshold(
                    applies_to=ThresholdAppliesTo.final_total,
                    metric=Metric.views,
                    op=">",
                    value=100_000,
                )
            ]
        ),
    )
    sql, params = build_query(intent)

    assert "v.views_count > %s" in sql
    assert "100000" not in sql
    assert params == (100_000,)
    assert _placeholder_count(sql) == len(params)


def test_build_snapshot_as_of_threshold_uses_snap_max_cte() -> None:
    intent = Intent(
        operation=Operation.count_videos,
        metric=None,
        date_range=DateRange(
            scope=DateRangeScope.snapshots_created_at,
            start_date=date(2025, 11, 28),
            end_date=date(2025, 11, 28),
            inclusive=True,
        ),
        filters=Filters(
            thresholds=[
                Threshold(
                    applies_to=ThresholdAppliesTo.snapshot_as_of,
                    metric=Metric.views,
                    op=">=",
                    value=10,
                )
            ]
        ),
    )
    sql, params = build_query(intent)

    assert sql.startswith("WITH snap_max AS")
    assert "JOIN snap_max sm ON sm.video_id = v.id" in sql
    assert "sm.views_count >= %s" in sql
    assert "10" not in sql
    assert params[0].isoformat() == "2025-11-28T00:00:00+00:00"
    assert params[1].isoformat() == "2025-11-29T00:00:00+00:00"
    assert params[2] == 10
    assert _placeholder_count(sql) == len(params)


def test_build_sum_delta_metric_shape() -> None:
    intent = Intent(
        operation=Operation.sum_delta_metric,
        metric=Metric.views,
        date_range=DateRange(
            scope=DateRangeScope.snapshots_created_at,
            start_date=date(2025, 11, 28),
            end_date=date(2025, 11, 28),
            inclusive=True,
        ),
        filters=Filters(
            creator_id="aca1061a9d324ecf8c3fa2bb32d7be63",
            thresholds=[
                Threshold(
                    applies_to=ThresholdAppliesTo.final_total,
                    metric=Metric.likes,
                    op=">=",
                    value=5,
                )
            ],
        ),
    )
    sql, params = build_query(intent)

    assert "SELECT COALESCE(SUM(s.delta_views_count), 0)::bigint" in sql
    assert "FROM video_snapshots s JOIN videos v ON v.id = s.video_id" in sql
    assert "s.created_at >= %s AND s.created_at < %s" in sql
    assert "v.creator_id = %s" in sql
    assert "v.likes_count >= %s" in sql
    assert "aca1061a9d324ecf8c3fa2bb32d7be63" not in sql
    assert _placeholder_count(sql) == len(params)


def test_build_sum_delta_metric_with_time_window_filters_created_at() -> None:
    intent = Intent(
        operation=Operation.sum_delta_metric,
        metric=Metric.views,
        date_range=DateRange(
            scope=DateRangeScope.snapshots_created_at,
            start_date=date(2025, 11, 28),
            end_date=date(2025, 11, 28),
            inclusive=True,
        ),
        time_window=TimeWindow(start_time=time(10), end_time=time(15)),
        filters=Filters(creator_id="c01"),
    )
    sql, params = build_query(intent)

    assert "s.created_at >= %s AND s.created_at <= %s" in sql
    assert params[0].isoformat() == "2025-11-28T10:00:00+00:00"
    assert params[1].isoformat() == "2025-11-28T15:00:00+00:00"
    assert params[2] == "c01"
    assert _placeholder_count(sql) == len(params)


def test_build_count_distinct_positive_delta_shape() -> None:
    intent = Intent(
        operation=Operation.count_distinct_videos_with_positive_delta,
        metric=Metric.views,
        date_range=DateRange(
            scope=DateRangeScope.snapshots_created_at,
            start_date=date(2025, 11, 27),
            end_date=date(2025, 11, 27),
            inclusive=True,
        ),
        filters=Filters(),
    )
    sql, params = build_query(intent)

    assert "SELECT COUNT(DISTINCT s.video_id)::bigint" in sql
    assert "s.delta_views_count > 0" in sql
    assert "s.created_at >= %s AND s.created_at < %s" in sql
    assert params[0].isoformat() == "2025-11-27T00:00:00+00:00"
    assert params[1].isoformat() == "2025-11-28T00:00:00+00:00"
    assert _placeholder_count(sql) == len(params)


def test_build_count_snapshots_with_negative_delta_shape() -> None:
    intent = Intent(
        operation=Operation.count_snapshots_with_negative_delta,
        metric=Metric.views,
        date_range=None,
        filters=Filters(),
    )
    sql, params = build_query(intent)

    assert "SELECT COUNT(*)::bigint" in sql
    assert "FROM video_snapshots s JOIN videos v ON v.id = s.video_id" in sql
    assert "s.delta_views_count < 0" in sql
    assert params == ()
    assert _placeholder_count(sql) == len(params)
