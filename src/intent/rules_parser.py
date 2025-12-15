"""Rules-based Russian NLQ parser (baseline).

This parser is intentionally strict and deterministic:
    - it only recognizes a limited set of patterns,
    - it rejects ambiguous/unsupported metric terms,
    - it produces an Intent validated by the Pydantic schema.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import time as dt_time

from src.intent import dates
from src.intent.dictionaries import (
    _COMPARATOR_MATCHES,
    METRIC_TERM_TO_METRIC,
    detect_single_metric,
    has_ambiguous_metric_term,
)
from src.intent.normalize import normalize_text
from src.intent.schema import (
    DateRange,
    DateRangeScope,
    Filters,
    Intent,
    Operation,
    Threshold,
    ThresholdAppliesTo,
    TimeWindow,
)


class RulesParserError(ValueError):
    """Raised when the rules parser cannot produce a valid intent."""


@dataclass(frozen=True)
class _ThresholdMatch:
    metric_term: str
    comparator_phrase: str
    value: int


_CREATOR_ID_RE = re.compile(
    r"\b(?:креатора?|creator)(?:\s+с)?\s*(?:id|айди|идентификатор|creator_id)?\s*[=:]?\s*(?P<id>[0-9a-z_\-]{3,})\b"
)

_TIME_WINDOW_RE = re.compile(
    r"\bс\s+(?P<h1>\d{1,2})(?:\s+(?P<m1>\d{2}))?\s+до\s+"
    r"(?P<h2>\d{1,2})(?:\s+(?P<m2>\d{2}))?\b"
)


def _has_all_time_phrase(text: str) -> bool:
    padded = f" {text} "
    return any(
        phrase in padded
        for phrase in (
            " за все время ",
            " за всё время ",
            " за весь период ",
            " all time ",
        )
    )


def _has_as_of_phrase(text: str) -> bool:
    # Keep this strict to avoid confusing "к" in other contexts.
    if " на тот момент " in f" {text} ":
        return True
    if " на дату " in f" {text} ":
        return True
    if re.search(r"\bк\s+\d{1,2}\s", text):
        return True
    return False


def _has_snapshot_term(text: str) -> bool:
    tokens = set(text.split())
    return (
            any(t.startswith("замер") for t in tokens)
            or any(t.startswith("измер") for t in tokens)
            or any(t.startswith("снимк") for t in tokens)
            or any(t.startswith("снапш") for t in tokens)
            or "snapshot" in tokens
            or "snapshots" in tokens
    )


def _has_negative_delta_phrase(text: str) -> bool:
    padded = f" {text} "
    return (
            "отриц" in text
            or " стало меньше " in padded
            or " уменьш" in padded
            or " сниз" in padded
            or " упал " in padded
            or " упало " in padded
            or " паден" in padded
    )


def _has_count_videos_phrase(text: str) -> bool:
    """Whether the wording is explicitly asking for a count of videos."""

    tokens = text.split()
    for idx, tok in enumerate(tokens):
        if tok not in {"сколько", "количество", "число"}:
            continue

        lookahead = tokens[idx + 1: idx + 4]
        if any(t.startswith("видео") for t in lookahead):
            return True
        if any(t.startswith("ролик") for t in lookahead):
            return True

    return False


def _has_count_creators_phrase(text: str) -> bool:
    """Whether the wording is explicitly asking for a count of creators."""

    tokens = text.split()
    for idx, tok in enumerate(tokens):
        if tok not in {"сколько", "количество", "число"}:
            continue

        lookahead = tokens[idx + 1: idx + 5]
        if any(t.startswith("креатор") for t in lookahead):
            return True
        if any(t.startswith("creator") for t in lookahead):
            return True
        if any(t.startswith("автор") for t in lookahead):
            return True

    return False


def _parse_time_parts(hour: str, minute: str | None) -> dt_time | None:
    """Parse a strict HH[:MM] fragment into a `datetime.time`."""

    try:
        hour_value = int(hour)
        minute_value = int(minute) if minute is not None else 0
        return dt_time(hour_value, minute_value)
    except ValueError:
        return None


def _extract_time_window(text: str) -> TimeWindow | None:
    """Extract a time window like "с 10:00 до 15:00" (normalized as "с 10 00 до 15 00")."""

    match = _TIME_WINDOW_RE.search(text)
    if not match:
        return None

    start_time = _parse_time_parts(match.group("h1"), match.group("m1"))
    end_time = _parse_time_parts(match.group("h2"), match.group("m2"))
    if start_time is None or end_time is None:
        return None

    return TimeWindow(start_time=start_time, end_time=end_time)


def _detect_operation(text: str) -> Operation:
    padded = f" {text} "
    tokens = set(text.split())
    metric = detect_single_metric(text)

    # Count snapshot measurements where per-snapshot delta is negative.
    if (
            _has_snapshot_term(text)
            and _has_negative_delta_phrase(text)
            and ("сколько" in tokens or "количество" in tokens or "число" in tokens)
    ):
        return Operation.count_snapshots_with_negative_delta

    # Sum of deltas ("growth on a day") intent.
    if (
            " на сколько " in padded
            or " насколько " in padded
            or " прирост " in padded
            or " вырос " in padded
            or " выросли " in padded
            or " увеличил" in padded
            or " увеличил" in padded
    ):
        return Operation.sum_delta_metric

    # Count distinct videos with positive delta.
    if "сколько" in tokens and "видео" in tokens and any(t.startswith("нов") for t in tokens):
        return Operation.count_distinct_videos_with_positive_delta

    # Count videos explicitly asked as "сколько/количество ... видео".
    if _has_count_videos_phrase(text):
        return Operation.count_videos

    # Count distinct creators matching filters.
    if _has_count_creators_phrase(text):
        return Operation.count_distinct_creators

    # Sum of final totals across videos (not deltas).
    if metric is not None and (
            not _has_count_videos_phrase(text) and not _has_count_creators_phrase(text)
    ):
        if (
                "в сумме" in padded
                or "суммар" in text
                or "общее" in tokens
                or "итого" in tokens
                or "всего" in tokens
                or "сколько" in tokens
                or "количество" in tokens
        ):
            return Operation.sum_total_metric

    if "сколько" in tokens or "количество" in tokens or "число" in tokens:
        if "видео" in tokens or any(t.startswith("видео") for t in tokens):
            return Operation.count_videos
        if any(t in {"ролик", "ролика", "ролики", "роликов"} for t in tokens):
            return Operation.count_videos

    raise RulesParserError("unsupported query")


def _extract_creator_id(text: str) -> str | None:
    match = _CREATOR_ID_RE.search(text)
    if not match:
        return None
    return match.group("id")


def _build_regex_alternation(phrases: list[str]) -> str:
    # Sort by length desc to prefer longer phrases (e.g. "не больше" over "больше").
    parts = sorted(phrases, key=lambda p: (-len(p), p))
    return "|".join(re.escape(p) for p in parts)


def _extract_threshold_matches(text: str) -> list[_ThresholdMatch]:
    metric_terms = sorted(METRIC_TERM_TO_METRIC.keys(), key=lambda s: (-len(s), s))
    metric_group = _build_regex_alternation(metric_terms)

    comparator_phrases = [m.phrase for m in _COMPARATOR_MATCHES]
    comparator_group = _build_regex_alternation(comparator_phrases)

    value_group = r"(?P<value>\d[\d\s_]*)"
    metric_group_named = rf"(?P<metric>{metric_group})"
    comp_group_named = rf"(?P<comp>{comparator_group})"

    patterns = [
        re.compile(rf"\b{comp_group_named}\s+{value_group}\s+{metric_group_named}\b"),
        re.compile(rf"\b{metric_group_named}\s+{comp_group_named}\s+{value_group}\b"),
    ]

    matches: list[_ThresholdMatch] = []
    for pat in patterns:
        for m in pat.finditer(text):
            raw_value = m.group("value")
            value = int(raw_value.replace(" ", "").replace("_", ""))
            matches.append(
                _ThresholdMatch(
                    metric_term=m.group("metric"),
                    comparator_phrase=m.group("comp"),
                    value=value,
                )
            )
    return matches


def _parse_thresholds(text: str, *, applies_to: ThresholdAppliesTo) -> list[Threshold]:
    parsed: list[Threshold] = []

    for match in _extract_threshold_matches(text):
        metric = METRIC_TERM_TO_METRIC[match.metric_term]

        op = None
        for cmp_match in _COMPARATOR_MATCHES:
            if cmp_match.phrase == match.comparator_phrase:
                op = cmp_match.op
                break
        if op is None:
            continue

        parsed.append(
            Threshold(
                applies_to=applies_to,
                metric=metric,
                op=op,
                value=match.value,
            )
        )

    # Deduplicate while preserving order.
    seen: set[tuple] = set()
    uniq: list[Threshold] = []
    for t in parsed:
        key = (t.applies_to, t.metric, t.op, t.value)
        if key in seen:
            continue
        seen.add(key)
        uniq.append(t)
    return uniq


def parse_intent(text: str) -> Intent:
    """Parse an input string into a validated Intent.

    Raises:
        RulesParserError: If the request is unsupported or ambiguous.
    """

    normalized = normalize_text(text)
    if not normalized:
        raise RulesParserError("empty input")

    if has_ambiguous_metric_term(normalized):
        raise RulesParserError("ambiguous/unsupported metric term")

    operation = _detect_operation(normalized)

    as_of = _has_as_of_phrase(normalized)
    applies_to = ThresholdAppliesTo.snapshot_as_of if as_of else ThresholdAppliesTo.final_total

    thresholds = _parse_thresholds(normalized, applies_to=applies_to)

    # Date parsing benefits from keeping punctuation (e.g. "10:00"), so parse from raw text.
    date_tuple = None if _has_all_time_phrase(normalized) else dates.parse_date_range(text)
    date_range = None
    if date_tuple is not None:
        start_date, end_date = date_tuple
        if operation in {
            Operation.count_videos,
            Operation.count_distinct_creators,
            Operation.sum_total_metric,
        }:
            scope = DateRangeScope.videos_published_at
        else:
            scope = DateRangeScope.snapshots_created_at

        if as_of and operation in {
            Operation.count_videos,
            Operation.count_distinct_creators,
            Operation.sum_total_metric,
        }:
            scope = DateRangeScope.snapshots_created_at
        date_range = DateRange(
            scope=scope,
            start_date=start_date,
            end_date=end_date,
            inclusive=True,
        )
    elif as_of:
        # "As-of" requires a date to define a snapshot window.
        raise RulesParserError("as-of threshold requires a date")

    creator_id = _extract_creator_id(normalized)

    intent_metric = None
    if operation not in {Operation.count_videos, Operation.count_distinct_creators}:
        intent_metric = detect_single_metric(normalized)
        if intent_metric is None:
            raise RulesParserError("metric is required/ambiguous")

    time_window = None
    if operation in {
        Operation.sum_delta_metric,
        Operation.count_distinct_videos_with_positive_delta,
        Operation.count_snapshots_with_negative_delta,
    }:
        time_window = _extract_time_window(normalized)

    try:
        return Intent(
            operation=operation,
            metric=intent_metric,
            date_range=date_range,
            time_window=time_window,
            filters=Filters(creator_id=creator_id, thresholds=thresholds),
        )
    except Exception as exc:  # noqa: BLE001 - caller handles unsupported inputs as parse failure
        raise RulesParserError(str(exc)) from exc
