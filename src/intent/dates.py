"""Russian date parsing utilities (UTC calendar days).

All user "dates" are interpreted as UTC calendar days:
    - single day: [day 00:00:00, next day 00:00:00)
    - inclusive ranges: [start 00:00:00, (end + 1 day) 00:00:00)
"""

from __future__ import annotations

import re
from datetime import UTC, date, datetime, time, timedelta

import dateparser
from dateparser.conf import Settings as DateparserSettings
from dateparser.search import search_dates

_DATEPARSER_SETTINGS = DateparserSettings().replace(
    STRICT_PARSING=True,
    DATE_ORDER="DMY",
    TIMEZONE="UTC",
    TO_TIMEZONE="UTC",
    RETURN_AS_TIMEZONE_AWARE=True,
)

_RU_MONTH_NAMES: tuple[str, ...] = (
    "января",
    "февраля",
    "марта",
    "апреля",
    "мая",
    "июня",
    "июля",
    "августа",
    "сентября",
    "октября",
    "ноября",
    "декабря",
)
_RU_MONTHS: dict[str, int] = {name: idx + 1 for idx, name in enumerate(_RU_MONTH_NAMES)}
_RU_MONTH_PATTERN = "|".join(_RU_MONTH_NAMES)

_YEAR_RE = re.compile(r"\b\d{4}\b")

_RANGE_SAME_MONTH_RE = re.compile(
    rf"\bс\s+(?P<d1>\d{{1,2}})\s+по\s+(?P<d2>\d{{1,2}})\s+"
    rf"(?P<m>{_RU_MONTH_PATTERN})\s+(?P<y>\d{{4}})\b"
)

_RANGE_MONTH_TO_MONTH_SAME_YEAR_RE = re.compile(
    rf"\bс\s+(?P<d1>\d{{1,2}})\s+(?P<m1>{_RU_MONTH_PATTERN})\s+по\s+"
    rf"(?P<d2>\d{{1,2}})\s+(?P<m2>{_RU_MONTH_PATTERN})\s+(?P<y>\d{{4}})\b"
)


def _parse_ru_date_fragment(fragment: str) -> date | None:
    dt = dateparser.parse(
        fragment,
        languages=["ru"],
        settings=_DATEPARSER_SETTINGS,
    )
    if not dt:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.date()


def _extract_yearful_dates(text: str) -> list[date]:
    results = search_dates(
        text,
        languages=["ru"],
        settings=_DATEPARSER_SETTINGS,
    )
    if not results:
        return []

    parsed: list[date] = []
    for matched, dt in results:
        if not _YEAR_RE.search(matched):
            continue
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=UTC)
        parsed.append(dt.date())
    return parsed


def parse_date_range(text: str) -> tuple[date, date] | None:
    """Parse a single day or an inclusive range from text.

    Returns:
        `(start_date, end_date)` (inclusive) if a date or range is found; otherwise `None`.
    """

    value = (text or "").strip().lower()
    if not value:
        return None

    match = _RANGE_SAME_MONTH_RE.search(value)
    if match:
        year = int(match.group("y"))
        month = _RU_MONTHS[match.group("m")]
        start = date(year, month, int(match.group("d1")))
        end = date(year, month, int(match.group("d2")))
        return (start, end) if start <= end else (end, start)

    match = _RANGE_MONTH_TO_MONTH_SAME_YEAR_RE.search(value)
    if match:
        year = int(match.group("y"))
        start = date(year, _RU_MONTHS[match.group("m1")], int(match.group("d1")))
        end = date(year, _RU_MONTHS[match.group("m2")], int(match.group("d2")))
        return (start, end) if start <= end else (end, start)

    yearful_dates = _extract_yearful_dates(value)
    if len(yearful_dates) >= 2:
        return yearful_dates[0], yearful_dates[1]
    if len(yearful_dates) == 1:
        d = yearful_dates[0]
        return d, d

    # Fallback: try parsing the whole string as a single date fragment.
    d = _parse_ru_date_fragment(value)
    if d:
        return d, d

    return None


def inclusive_dates_to_half_open(start: date, end: date) -> tuple[datetime, datetime]:
    """Convert inclusive day range into a half-open UTC datetime interval."""

    start_dt = datetime.combine(start, time.min, tzinfo=UTC)
    end_dt = datetime.combine(end + timedelta(days=1), time.min, tzinfo=UTC)
    return start_dt, end_dt
