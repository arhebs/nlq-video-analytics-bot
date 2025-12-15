"""Tests for RU date parsing and UTC half-open interval conversion."""

from __future__ import annotations

from datetime import UTC, date

from src.intent.dates import inclusive_dates_to_half_open, parse_date_range


def test_parse_single_day_ru() -> None:
    start, end = parse_date_range("28 ноября 2025")
    assert start == date(2025, 11, 28)
    assert end == date(2025, 11, 28)


def test_parse_inclusive_range_ru_same_month() -> None:
    start, end = parse_date_range("с 1 по 5 ноября 2025 включительно")
    assert start == date(2025, 11, 1)
    assert end == date(2025, 11, 5)


def test_inclusive_to_half_open_conversion() -> None:
    start_dt, end_dt = inclusive_dates_to_half_open(date(2025, 11, 1), date(2025, 11, 5))
    assert start_dt.isoformat() == "2025-11-01T00:00:00+00:00"
    assert end_dt.isoformat() == "2025-11-06T00:00:00+00:00"
    assert start_dt.tzinfo == UTC
    assert end_dt.tzinfo == UTC


def test_parse_month_range_ru() -> None:
    start, end = parse_date_range("в июне 2025 года")
    assert start == date(2025, 6, 1)
    assert end == date(2025, 6, 30)
