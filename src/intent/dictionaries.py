"""Russian dictionaries for metrics and comparators.

These mappings are used by the rules-based parser and should remain small and deterministic.
Ambiguous metric terms (e.g. "реакции") are treated as unsupported.
"""

from __future__ import annotations

from dataclasses import dataclass

from src.intent.schema import Comparator, Metric

AMBIGUOUS_METRIC_TERMS: set[str] = {
    # Treat "reactions" as ambiguous/unsupported in MVP as required by spec.
    "реакции",
    "реакция",
    "реакций",
}

METRIC_SYNONYMS: dict[Metric, tuple[str, ...]] = {
    Metric.views: ("просмотры", "просмотр", "просмотров", "views"),
    Metric.likes: ("лайки", "лайк", "лайков", "нравится", "сердечки"),
    Metric.comments: ("комментарии", "комментарий", "коммент", "комменты", "комментариев"),
    Metric.reports: ("жалобы", "жалоба", "жалоб", "пожаловаться", "репорт", "репорты"),
}

METRIC_TERM_TO_METRIC: dict[str, Metric] = {
    term: metric for metric, terms in METRIC_SYNONYMS.items() for term in terms
}

COMPARATOR_SYNONYMS: dict[Comparator, tuple[str, ...]] = {
    ">": ("больше чем", "более чем", "свыше", "больше"),
    ">=": ("по меньшей мере", "как минимум", "не меньше", "не менее"),
    "<": ("меньше чем", "менее чем", "меньше"),
    "<=": ("не превышает", "не больше", "не более", "максимум"),
    "=": ("равняется", "равно", "ровно"),
}


@dataclass(frozen=True)
class ComparatorMatch:
    """A concrete RU phrase matched to a canonical SQL comparator operator."""

    op: Comparator
    phrase: str


_COMPARATOR_MATCHES: list[ComparatorMatch] = sorted(
    (ComparatorMatch(op=op, phrase=phrase) for op, phrases in COMPARATOR_SYNONYMS.items() for phrase in phrases),
    key=lambda m: (-len(m.phrase), m.phrase),
)


def find_metrics(text: str) -> set[Metric]:
    """Return all metrics explicitly mentioned in the text (by known synonyms)."""

    tokens = set((text or "").split())
    return {METRIC_TERM_TO_METRIC[t] for t in tokens if t in METRIC_TERM_TO_METRIC}


def has_ambiguous_metric_term(text: str) -> bool:
    """Whether the text contains an ambiguous metric term (unsupported in MVP)."""

    tokens = set((text or "").split())
    return any(t in AMBIGUOUS_METRIC_TERMS for t in tokens)


def detect_single_metric(text: str) -> Metric | None:
    """Detect exactly one metric in text.

    Returns:
        The metric if exactly one is present; otherwise `None`.
    """

    metrics = find_metrics(text)
    if len(metrics) == 1:
        return next(iter(metrics))
    return None


def detect_comparator(text: str) -> Comparator | None:
    """Detect a comparator operator in text (>, >=, <, <=, =)."""

    padded = f" {text} "
    for match in _COMPARATOR_MATCHES:
        if f" {match.phrase} " in padded:
            return match.op
    return None
