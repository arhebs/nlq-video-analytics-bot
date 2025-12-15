"""Deterministic SQL builder.

The builder converts a validated `Intent` into a parameterized SQL query. Identifiers (columns,
tables, operators) are strictly allowlisted; only values become bound parameters.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from src.intent.dates import inclusive_dates_to_half_open
from src.intent.schema import (
    Comparator,
    DateRange,
    DateRangeScope,
    Intent,
    Metric,
    Operation,
    Threshold,
    ThresholdAppliesTo,
)
from src.sql.columns import SNAPSHOT_DELTA_COLUMNS, SNAPSHOT_TOTAL_COLUMNS, VIDEO_TOTAL_COLUMNS


class SQLBuilderError(ValueError):
    """Raised when an Intent cannot be converted into deterministic SQL."""


_ALLOWED_OPERATORS: dict[Comparator, str] = {
    ">": ">",
    ">=": ">=",
    "<": "<",
    "<=": "<=",
    "=": "=",
}


@dataclass(frozen=True)
class BuiltQuery:
    """A parameterized SQL query ready for execution."""

    sql: str
    params: tuple[Any, ...]


def _half_open_bounds(date_range: DateRange) -> tuple[datetime, datetime]:
    return inclusive_dates_to_half_open(date_range.start_date, date_range.end_date)


def _where_and(clauses: list[str]) -> str:
    if not clauses:
        return ""
    return "WHERE " + " AND ".join(clauses)


def _final_total_thresholds(thresholds: Iterable[Threshold]) -> list[Threshold]:
    return [t for t in thresholds if t.applies_to == ThresholdAppliesTo.final_total]


def _snapshot_as_of_thresholds(thresholds: Iterable[Threshold]) -> list[Threshold]:
    return [t for t in thresholds if t.applies_to == ThresholdAppliesTo.snapshot_as_of]


def _build_threshold_clause(
        *,
        table_alias: str,
        metric: Metric,
        op: Comparator,
        value: int,
        column_map: dict[Metric, str],
) -> tuple[str, list[Any]]:
    column = column_map[metric]
    operator = _ALLOWED_OPERATORS[op]
    return f"{table_alias}.{column} {operator} %s", [value]


def _build_date_clause(column_ref: str, date_range: DateRange) -> tuple[str, list[Any]]:
    start_dt, end_dt = _half_open_bounds(date_range)
    return f"{column_ref} >= %s AND {column_ref} < %s", [start_dt, end_dt]


def _build_snap_max_cte(date_range: DateRange) -> tuple[str, list[Any]]:
    if date_range.scope != DateRangeScope.snapshots_created_at:
        raise SQLBuilderError("snap_max CTE requires snapshots_created_at scope")

    start_dt, end_dt = _half_open_bounds(date_range)
    sql = (
        "WITH snap_max AS ("
        " SELECT s.video_id,"
        "        MAX(s.views_count) AS views_count,"
        "        MAX(s.likes_count) AS likes_count,"
        "        MAX(s.comments_count) AS comments_count,"
        "        MAX(s.reports_count) AS reports_count"
        "   FROM video_snapshots s"
        "  WHERE s.created_at >= %s AND s.created_at < %s"
        "  GROUP BY s.video_id"
        ") "
    )
    return sql, [start_dt, end_dt]


def _threshold_context(intent: Intent) -> tuple[list[Threshold], list[Threshold], str, list[Any]]:
    final_thresholds = _final_total_thresholds(intent.filters.thresholds)
    snapshot_thresholds = _snapshot_as_of_thresholds(intent.filters.thresholds)

    if not snapshot_thresholds:
        return final_thresholds, snapshot_thresholds, "", []

    if intent.date_range is None:
        raise SQLBuilderError("snapshot_as_of thresholds require date_range")

    cte_sql, cte_params = _build_snap_max_cte(intent.date_range)
    return final_thresholds, snapshot_thresholds, cte_sql, cte_params


def _from_snapshots_with_videos(snapshot_thresholds: list[Threshold]) -> str:
    from_sql = "FROM video_snapshots s JOIN videos v ON v.id = s.video_id"
    if snapshot_thresholds:
        from_sql += " JOIN snap_max sm ON sm.video_id = s.video_id"
    return from_sql


def _append_creator_filter(
        clauses: list[str],
        params: list[Any],
        *,
        creator_id: str | None,
) -> None:
    if creator_id is None:
        return
    clauses.append("v.creator_id = %s")
    params.append(creator_id)


def _append_thresholds(
        clauses: list[str],
        params: list[Any],
        thresholds: Iterable[Threshold],
        *,
        table_alias: str,
        column_map: dict[Metric, str],
) -> None:
    for t in thresholds:
        clause, p = _build_threshold_clause(
            table_alias=table_alias,
            metric=t.metric,
            op=t.op,
            value=t.value,
            column_map=column_map,
        )
        clauses.append(clause)
        params.extend(p)


def _snapshot_query_context(
        intent: Intent,
        *,
        initial_clauses: list[str] | None = None,
) -> tuple[str, list[str], list[Any], str]:
    clauses: list[str] = list(initial_clauses or [])
    params: list[Any] = []

    final_thresholds, snapshot_thresholds, cte_sql, cte_params = _threshold_context(intent)
    params.extend(cte_params)

    from_sql = _from_snapshots_with_videos(snapshot_thresholds)

    # Date filter on snapshots.
    if intent.date_range is not None:
        clause, p = _build_date_clause("s.created_at", intent.date_range)
        clauses.append(clause)
        params.extend(p)

    # Creator filter.
    _append_creator_filter(clauses, params, creator_id=intent.filters.creator_id)

    # Thresholds.
    _append_thresholds(
        clauses,
        params,
        final_thresholds,
        table_alias="v",
        column_map=VIDEO_TOTAL_COLUMNS,
    )
    _append_thresholds(
        clauses,
        params,
        snapshot_thresholds,
        table_alias="sm",
        column_map=SNAPSHOT_TOTAL_COLUMNS,
    )

    return from_sql, clauses, params, cte_sql


def _video_query_context(intent: Intent) -> tuple[str, list[str], list[Any], str]:
    clauses: list[str] = []
    params: list[Any] = []

    final_thresholds, snapshot_thresholds, cte_sql, cte_params = _threshold_context(intent)
    params.extend(cte_params)

    from_sql = "FROM videos v"
    if snapshot_thresholds:
        from_sql += " JOIN snap_max sm ON sm.video_id = v.id"

    _append_creator_filter(clauses, params, creator_id=intent.filters.creator_id)

    if intent.date_range is not None:
        if intent.date_range.scope == DateRangeScope.videos_published_at:
            clause, p = _build_date_clause("v.video_created_at", intent.date_range)
            clauses.append(clause)
            params.extend(p)
        elif (
                intent.date_range.scope == DateRangeScope.snapshots_created_at
                and not snapshot_thresholds
        ):
            # Apply the date filter via snapshots existence, but still query over videos.
            clause, p = _build_date_clause("s.created_at", intent.date_range)
            clauses.append(
                "EXISTS (SELECT 1 FROM video_snapshots s WHERE s.video_id = v.id AND "
                + clause
                + ")"
            )
            params.extend(p)

    _append_thresholds(
        clauses,
        params,
        final_thresholds,
        table_alias="v",
        column_map=VIDEO_TOTAL_COLUMNS,
    )
    _append_thresholds(
        clauses,
        params,
        snapshot_thresholds,
        table_alias="sm",
        column_map=SNAPSHOT_TOTAL_COLUMNS,
    )

    return from_sql, clauses, params, cte_sql


def build_query(intent: Intent) -> tuple[str, tuple[Any, ...]]:
    """Build a scalar SQL query + params from a validated Intent."""

    builders = {
        Operation.count_videos: _build_count_videos,
        Operation.sum_total_metric: _build_sum_total_metric,
        Operation.sum_delta_metric: _build_sum_delta_metric,
        Operation.count_distinct_videos_with_positive_delta: _build_count_distinct_positive_delta,
        Operation.count_snapshots_with_negative_delta: _build_count_snapshots_with_negative_delta,
    }

    try:
        built = builders[intent.operation](intent)
    except KeyError as exc:
        raise SQLBuilderError(f"Unsupported operation: {intent.operation}") from exc

    return built.sql, built.params


def _build_count_videos(intent: Intent) -> BuiltQuery:
    if intent.metric is not None:
        raise SQLBuilderError("count_videos expects metric=null")

    from_sql, clauses, params, cte_sql = _video_query_context(intent)

    sql = f"{cte_sql}SELECT COUNT(*)::bigint {from_sql} {_where_and(clauses)}".strip()
    return BuiltQuery(sql=sql, params=tuple(params))


def _build_sum_total_metric(intent: Intent) -> BuiltQuery:
    if intent.metric is None:
        raise SQLBuilderError("sum_total_metric requires a metric")

    metric_col = VIDEO_TOTAL_COLUMNS[intent.metric]

    from_sql, clauses, params, cte_sql = _video_query_context(intent)

    sql = (
        f"{cte_sql}SELECT COALESCE(SUM(v.{metric_col}), 0)::bigint {from_sql} "
        f"{_where_and(clauses)}"
    ).strip()
    return BuiltQuery(sql=sql, params=tuple(params))


def _build_sum_delta_metric(intent: Intent) -> BuiltQuery:
    if intent.metric is None:
        raise SQLBuilderError("sum_delta_metric requires a metric")

    delta_col = SNAPSHOT_DELTA_COLUMNS[intent.metric]

    from_sql, clauses, params, cte_sql = _snapshot_query_context(intent)

    sql = (
        f"{cte_sql}SELECT COALESCE(SUM(s.{delta_col}), 0)::bigint {from_sql} {_where_and(clauses)}"
    ).strip()
    return BuiltQuery(sql=sql, params=tuple(params))


def _build_count_distinct_positive_delta(intent: Intent) -> BuiltQuery:
    if intent.metric is None:
        raise SQLBuilderError("count_distinct_videos_with_positive_delta requires a metric")

    delta_col = SNAPSHOT_DELTA_COLUMNS[intent.metric]

    from_sql, clauses, params, cte_sql = _snapshot_query_context(
        intent,
        initial_clauses=[f"s.{delta_col} > 0"],
    )

    sql = (
        f"{cte_sql}SELECT COUNT(DISTINCT s.video_id)::bigint {from_sql} "
        f"{_where_and(clauses)}"
    ).strip()
    return BuiltQuery(sql=sql, params=tuple(params))


def _build_count_snapshots_with_negative_delta(intent: Intent) -> BuiltQuery:
    if intent.metric is None:
        raise SQLBuilderError("count_snapshots_with_negative_delta requires a metric")

    delta_col = SNAPSHOT_DELTA_COLUMNS[intent.metric]

    from_sql, clauses, params, cte_sql = _snapshot_query_context(
        intent,
        initial_clauses=[f"s.{delta_col} < 0"],
    )

    sql = f"{cte_sql}SELECT COUNT(*)::bigint {from_sql} {_where_and(clauses)}".strip()
    return BuiltQuery(sql=sql, params=tuple(params))
