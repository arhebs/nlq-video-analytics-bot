"""Tests for RU metric/comparator dictionaries and ambiguity detection."""

from __future__ import annotations

from src.intent.dictionaries import (
    detect_comparator,
    detect_single_metric,
    has_ambiguous_metric_term,
)
from src.intent.schema import Metric


def test_metric_mapping_ru_synonyms() -> None:
    assert detect_single_metric("сколько просмотров") == Metric.views
    assert detect_single_metric("сколько лайков") == Metric.likes
    assert detect_single_metric("сколько комментариев") == Metric.comments
    assert detect_single_metric("сколько жалоб") == Metric.reports


def test_comparator_mapping_ru_phrases() -> None:
    assert detect_comparator("больше 10") == ">"
    assert detect_comparator("не больше 10") == "<="
    assert detect_comparator("не менее 10") == ">="
    assert detect_comparator("меньше 10") == "<"
    assert detect_comparator("ровно 10") == "="


def test_ambiguous_metric_is_detected() -> None:
    assert has_ambiguous_metric_term("сколько реакции")
    assert has_ambiguous_metric_term("сколько реакций")
    assert has_ambiguous_metric_term("сколько реакции и просмотры")  # still ambiguous in MVP
