"""Tests for the deterministic rules-based Russian intent parser."""

from __future__ import annotations

import pytest

from src.intent.rules_parser import RulesParserError, parse_intent
from src.intent.schema import (
    DateRangeScope,
    Metric,
    Operation,
    ThresholdAppliesTo,
)


def _assert_views_delta_growth_on_2025_11_28(intent: object) -> None:
    assert getattr(intent, "operation", None) == Operation.sum_delta_metric
    assert getattr(intent, "metric", None) == Metric.views
    date_range = getattr(intent, "date_range", None)
    assert date_range is not None
    assert date_range.scope == DateRangeScope.snapshots_created_at
    assert date_range.start_date.isoformat() == "2025-11-28"
    assert date_range.end_date.isoformat() == "2025-11-28"


def _assert_final_views_gt_100k_threshold(intent: object) -> None:
    filters = getattr(intent, "filters", None)
    assert filters is not None

    thresholds = getattr(filters, "thresholds", None)
    assert thresholds is not None
    assert len(thresholds) == 1

    t = thresholds[0]
    assert t.applies_to == ThresholdAppliesTo.final_total
    assert t.metric == Metric.views
    assert t.op == ">"
    assert t.value == 100_000


def test_parse_total_videos() -> None:
    intent = parse_intent("Сколько всего видео есть в системе?")
    assert intent.operation == Operation.count_videos
    assert intent.metric is None
    assert intent.date_range is None
    assert intent.filters.creator_id is None
    assert intent.filters.thresholds == []


def test_parse_creator_and_inclusive_range() -> None:
    intent = parse_intent(
        "Сколько видео у креатора с id aca1061a9d324ecf8c3fa2bb32d7be63 "
        "вышло с 1 по 5 ноября 2025 включительно?"
    )
    assert intent.operation == Operation.count_videos
    assert intent.metric is None
    assert intent.filters.creator_id == "aca1061a9d324ecf8c3fa2bb32d7be63"
    assert intent.date_range is not None
    assert intent.date_range.scope == DateRangeScope.videos_published_at
    assert intent.date_range.start_date.isoformat() == "2025-11-01"
    assert intent.date_range.end_date.isoformat() == "2025-11-05"


def test_parse_final_total_threshold() -> None:
    intent = parse_intent("Сколько видео набрало больше 100 000 просмотров за всё время?")
    assert intent.operation == Operation.count_videos
    assert intent.metric is None
    _assert_final_views_gt_100k_threshold(intent)


def test_parse_sum_delta_metric_on_day() -> None:
    intent = parse_intent("На сколько просмотров в сумме выросли все видео 28 ноября 2025?")
    _assert_views_delta_growth_on_2025_11_28(intent)


def test_parse_sum_delta_metric_with_time_window() -> None:
    creator_id = "cd87be38b50b4fdd8342bb3c383f3c7d"
    intent = parse_intent(
        "На сколько просмотров суммарно выросли все видео креатора с id "
        f"{creator_id} "
        "в промежутке с 10:00 до 15:00 28 ноября 2025 года?"
    )
    _assert_views_delta_growth_on_2025_11_28(intent)
    assert intent.time_window is not None
    assert intent.time_window.start_time.isoformat() == "10:00:00"
    assert intent.time_window.end_time.isoformat() == "15:00:00"


def test_parse_sum_total_metric_for_month_published() -> None:
    intent = parse_intent(
        "Какое суммарное количество просмотров набрали все видео, опубликованные в июне 2025 года?"
    )
    assert intent.operation == Operation.sum_total_metric
    assert intent.metric == Metric.views
    assert intent.date_range is not None
    assert intent.date_range.scope == DateRangeScope.videos_published_at
    assert intent.date_range.start_date.isoformat() == "2025-06-01"
    assert intent.date_range.end_date.isoformat() == "2025-06-30"


def test_parse_distinct_videos_positive_delta() -> None:
    intent = parse_intent("Сколько разных видео получали новые просмотры 27 ноября 2025?")
    assert intent.operation == Operation.count_distinct_videos_with_positive_delta
    assert intent.metric == Metric.views
    assert intent.date_range is not None
    assert intent.date_range.scope == DateRangeScope.snapshots_created_at
    assert intent.date_range.start_date.isoformat() == "2025-11-27"


def test_parse_count_snapshots_with_negative_delta() -> None:
    intent = parse_intent(
        "Сколько всего есть замеров статистики (по всем видео), "
        "в которых число просмотров за час оказалось отрицательным?"
    )
    assert intent.operation == Operation.count_snapshots_with_negative_delta
    assert intent.metric == Metric.views
    assert intent.date_range is None


def test_parse_count_distinct_creators_with_threshold() -> None:
    intent = parse_intent(
        "Сколько разных креаторов имеют хотя бы одно видео, "
        "которое в итоге набрало больше 100 000 просмотров?"
    )
    assert intent.operation == Operation.count_distinct_creators
    assert intent.metric is None
    assert intent.date_range is None
    _assert_final_views_gt_100k_threshold(intent)


def test_parse_count_distinct_publish_days_in_month_for_creator() -> None:
    intent = parse_intent(
        "Для креатора с id aca1061a9d324ecf8c3fa2bb32d7be63 посчитай, "
        "в скольких разных календарных днях ноября 2025 года "
        "он публиковал хотя бы одно видео."
    )
    assert intent.operation == Operation.count_distinct_publish_days
    assert intent.metric is None
    assert intent.filters.creator_id == "aca1061a9d324ecf8c3fa2bb32d7be63"
    assert intent.date_range is not None
    assert intent.date_range.scope == DateRangeScope.videos_published_at
    assert intent.date_range.start_date.isoformat() == "2025-11-01"
    assert intent.date_range.end_date.isoformat() == "2025-11-30"


def test_reactions_is_unsupported() -> None:
    with pytest.raises(RulesParserError):
        parse_intent("Сколько реакций было 28 ноября 2025?")
