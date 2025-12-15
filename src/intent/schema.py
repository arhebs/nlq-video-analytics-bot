"""Intent JSON schema (Pydantic models).

This schema is the contract between the NL parser (rules/LLM) and the deterministic SQL builder.
All parsing must validate against these models; otherwise the request is treated as unsupported.
"""

from __future__ import annotations

from datetime import date, time
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class Operation(StrEnum):
    """Supported query operation families."""

    count_videos = "count_videos"
    count_distinct_creators = "count_distinct_creators"
    count_distinct_publish_days = "count_distinct_publish_days"
    sum_total_metric = "sum_total_metric"
    sum_delta_metric = "sum_delta_metric"
    count_distinct_videos_with_positive_delta = "count_distinct_videos_with_positive_delta"
    count_snapshots_with_negative_delta = "count_snapshots_with_negative_delta"


class Metric(StrEnum):
    """Supported metric names."""

    views = "views"
    likes = "likes"
    comments = "comments"
    reports = "reports"


class DateRangeScope(StrEnum):
    """Which timestamp column the date filter applies to."""

    videos_published_at = "videos_published_at"
    snapshots_created_at = "snapshots_created_at"


class ThresholdAppliesTo(StrEnum):
    """Where a threshold is evaluated."""

    final_total = "final_total"
    snapshot_as_of = "snapshot_as_of"


Comparator = Literal[">", ">=", "<", "<=", "="]


class DateRange(BaseModel):
    """An inclusive calendar-day range as entered by a user.

    The SQL builder must interpret this inclusive range as a half-open UTC interval:
    `[start_date 00:00:00, (end_date + 1 day) 00:00:00)`.
    """

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    scope: DateRangeScope
    start_date: date
    end_date: date
    inclusive: Literal[True] = True

    @model_validator(mode="after")
    def validate_range(self) -> DateRange:
        """Validate that the inclusive range is well-formed (`start_date <= end_date`)."""

        if self.start_date > self.end_date:
            raise ValueError("start_date must be <= end_date")
        return self


class TimeWindow(BaseModel):
    """A time-of-day filter applied within a single UTC calendar day."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    start_time: time
    end_time: time

    @model_validator(mode="after")
    def validate_range(self) -> TimeWindow:
        """Validate that the time window is well-formed (`start_time <= end_time`)."""

        if self.start_time > self.end_time:
            raise ValueError("start_time must be <= end_time")
        return self


class Threshold(BaseModel):
    """A numeric threshold filter combined with AND across all thresholds."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    applies_to: ThresholdAppliesTo
    metric: Metric
    op: Comparator
    value: int

    @model_validator(mode="after")
    def validate_value(self) -> Threshold:
        """Validate threshold value fits into Postgres BIGINT bounds."""

        # Counts are non-negative in the dataset; negative thresholds are allowed but rarely useful.
        # Keep the validation minimal: ensure it's an int (already enforced) and fits common SQL
        # types.
        if self.value < -(2 ** 63) or self.value > 2 ** 63 - 1:
            raise ValueError("value is out of supported BIGINT range")
        return self


class Filters(BaseModel):
    """Query filters combined using logical AND."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    creator_id: str | None = None
    thresholds: list[Threshold] = Field(default_factory=list)


class Intent(BaseModel):
    """A fully validated query intent."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    operation: Operation
    metric: Metric | None = None
    date_range: DateRange | None = None
    time_window: TimeWindow | None = None
    filters: Filters = Field(default_factory=Filters)

    @model_validator(mode="after")
    def validate_semantics(self) -> Intent:
        """Enforce cross-field invariants required by the project semantics."""

        if self.operation in {
            Operation.count_videos,
            Operation.count_distinct_creators,
            Operation.count_distinct_publish_days,
        }:
            if self.metric is not None:
                raise ValueError("metric must be null for count operations")
        else:
            if self.metric is None:
                raise ValueError("metric is required for metric-based operations")

        if self.operation == Operation.count_distinct_publish_days:
            if self.date_range is None:
                raise ValueError("date_range is required for operation=count_distinct_publish_days")
            if self.date_range.scope != DateRangeScope.videos_published_at:
                raise ValueError(
                    "count_distinct_publish_days requires date_range.scope=videos_published_at"
                )

        has_snapshot_as_of = any(
            t.applies_to == ThresholdAppliesTo.snapshot_as_of for t in self.filters.thresholds
        )
        if has_snapshot_as_of:
            if self.date_range is None:
                raise ValueError("snapshot_as_of thresholds require a date_range")
            if self.date_range.scope != DateRangeScope.snapshots_created_at:
                raise ValueError(
                    "snapshot_as_of thresholds require date_range.scope=snapshots_created_at"
                )

        if self.time_window is not None:
            if self.date_range is None:
                raise ValueError("time_window requires a date_range")
            if self.date_range.scope != DateRangeScope.snapshots_created_at:
                raise ValueError("time_window requires date_range.scope=snapshots_created_at")
            if self.date_range.start_date != self.date_range.end_date:
                raise ValueError("time_window requires a single-day date_range")
            if self.operation not in {
                Operation.sum_delta_metric,
                Operation.count_distinct_videos_with_positive_delta,
                Operation.count_snapshots_with_negative_delta,
            }:
                raise ValueError("time_window is only supported for snapshot-based operations")

        if self.operation in {
            Operation.sum_delta_metric,
            Operation.count_distinct_videos_with_positive_delta,
            Operation.count_snapshots_with_negative_delta,
        }:
            if (
                    self.date_range is not None
                    and self.date_range.scope != DateRangeScope.snapshots_created_at
            ):
                raise ValueError("delta operations require date_range.scope=snapshots_created_at")

        return self


def intent_from_obj(obj: Any) -> Intent:
    """Validate and parse an Intent from an arbitrary decoded JSON object."""

    return Intent.model_validate(obj)
