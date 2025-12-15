"""Text normalization for deterministic intent parsing."""

from __future__ import annotations

import re

_NON_WORD_RE = re.compile(r"[^0-9a-zа-я_\-\s]+", flags=re.IGNORECASE)
_MULTISPACE_RE = re.compile(r"\s+")


def normalize_text(text: str) -> str:
    """Normalize user text for rules-based parsing.

    Normalization is intentionally conservative:
        - Lowercase.
        - Replace `ё` -> `е`.
        - Replace punctuation with spaces.
        - Collapse whitespace.

    The goal is deterministic tokenization, not linguistic lemmatization.
    """

    value = (text or "").strip().lower()
    value = value.replace("ё", "е")

    # Normalize common unicode dashes to ASCII hyphen.
    value = value.replace("—", "-").replace("–", "-")

    # Treat quotes/backticks as separators but preserve the contents (e.g. IDs).
    value = value.replace("`", " ").replace('"', " ").replace("'", " ")

    value = _NON_WORD_RE.sub(" ", value)
    value = _MULTISPACE_RE.sub(" ", value).strip()
    return value
