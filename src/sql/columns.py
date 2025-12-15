"""Allowlisted SQL identifiers.

All column names referenced in generated SQL must come from these mappings; no user-provided
identifier should ever be interpolated into SQL.
"""

from __future__ import annotations

from src.intent.schema import Metric

VIDEO_TOTAL_COLUMNS: dict[Metric, str] = {
    Metric.views: "views_count",
    Metric.likes: "likes_count",
    Metric.comments: "comments_count",
    Metric.reports: "reports_count",
}

SNAPSHOT_TOTAL_COLUMNS: dict[Metric, str] = {
    Metric.views: "views_count",
    Metric.likes: "likes_count",
    Metric.comments: "comments_count",
    Metric.reports: "reports_count",
}

SNAPSHOT_DELTA_COLUMNS: dict[Metric, str] = {
    Metric.views: "delta_views_count",
    Metric.likes: "delta_likes_count",
    Metric.comments: "delta_comments_count",
    Metric.reports: "delta_reports_count",
}
