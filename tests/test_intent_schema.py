"""Tests for the strict Intent Pydantic schema and its cross-field invariants."""

from __future__ import annotations

from datetime import date, time

import pytest

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


def test_intent_requires_metric_for_delta_ops() -> None:
    with pytest.raises(ValueError):
        Intent(
            operation=Operation.sum_delta_metric,
            metric=None,
            date_range=DateRange(
                scope=DateRangeScope.snapshots_created_at,
                start_date=date(2025, 11, 28),
                end_date=date(2025, 11, 28),
                inclusive=True,
            ),
            filters=Filters(),
        )


def test_intent_requires_metric_for_sum_total_metric() -> None:
    with pytest.raises(ValueError):
        Intent(operation=Operation.sum_total_metric, metric=None)


def test_intent_forbids_metric_for_count_videos() -> None:
    with pytest.raises(ValueError):
        Intent(operation=Operation.count_videos, metric=Metric.views)


def test_snapshot_as_of_threshold_requires_snapshot_scope() -> None:
    with pytest.raises(ValueError):
        Intent(
            operation=Operation.count_videos,
            metric=None,
            date_range=DateRange(
                scope=DateRangeScope.videos_published_at,
                start_date=date(2025, 11, 28),
                end_date=date(2025, 11, 28),
                inclusive=True,
            ),
            filters=Filters(
                thresholds=[
                    Threshold(
                        applies_to=ThresholdAppliesTo.snapshot_as_of,
                        metric=Metric.views,
                        op=">",
                        value=100,
                    )
                ]
            ),
        )


def test_negative_delta_snapshot_op_requires_snapshot_scope_when_dated() -> None:
    with pytest.raises(ValueError):
        Intent(
            operation=Operation.count_snapshots_with_negative_delta,
            metric=Metric.views,
            date_range=DateRange(
                scope=DateRangeScope.videos_published_at,
                start_date=date(2025, 11, 28),
                end_date=date(2025, 11, 28),
                inclusive=True,
            ),
            filters=Filters(),
        )


def test_time_window_requires_date_range() -> None:
    with pytest.raises(ValueError):
        Intent(
            operation=Operation.sum_delta_metric,
            metric=Metric.views,
            time_window=TimeWindow(start_time=time(10), end_time=time(15)),
            filters=Filters(),
        )


def test_time_window_requires_single_day_snapshot_range() -> None:
    with pytest.raises(ValueError):
        Intent(
            operation=Operation.sum_delta_metric,
            metric=Metric.views,
            date_range=DateRange(
                scope=DateRangeScope.snapshots_created_at,
                start_date=date(2025, 11, 27),
                end_date=date(2025, 11, 28),
                inclusive=True,
            ),
            time_window=TimeWindow(start_time=time(10), end_time=time(15)),
            filters=Filters(),
        )
