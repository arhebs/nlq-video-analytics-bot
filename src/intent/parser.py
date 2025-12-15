"""Intent parser orchestration (LLM optional; rules-based fallback)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from src.intent.llm_parser import LLMParserError, llm_config_from_env, parse_intent_json_via_llm
from src.intent.rules_parser import RulesParserError
from src.intent.rules_parser import parse_intent as parse_rules_intent
from src.intent.schema import Intent, intent_from_obj


class IntentParserError(ValueError):
    """Raised when no parser can produce a valid intent."""


ParseSource = Literal["llm", "rules"]


@dataclass(frozen=True)
class ParseResult:
    """Validated intent plus information about which parser produced it."""

    intent: Intent
    source: ParseSource


def parse_intent_with_source(
        text: str,
        *,
        llm_enabled: bool,
        llm_api_key: str | None = None,
) -> ParseResult:
    """Parse text into an Intent object.

    Strategy:
        1) If LLM mode is enabled, ask the LLM to produce strict Intent JSON and validate it.
        2) On any failure/invalid JSON, fallback to the deterministic rules' parser.
        3) If rules parsing fails too, raise `IntentParserError`.
    """

    if llm_enabled:
        try:
            cfg = llm_config_from_env(api_key=llm_api_key)
            obj: dict[str, Any] = parse_intent_json_via_llm(text, config=cfg)
            intent = intent_from_obj(obj)
            return ParseResult(intent=intent, source="llm")
        except (LLMParserError, ValueError):
            # Invalid LLM output must never crash the pipeline; fall back to rules.
            pass

    try:
        intent = parse_rules_intent(text)
        return ParseResult(intent=intent, source="rules")
    except RulesParserError as exc:
        raise IntentParserError(str(exc)) from exc


def parse_intent(text: str, *, llm_enabled: bool, llm_api_key: str | None = None) -> Intent:
    """Parse text into a validated Intent object (convenience wrapper)."""

    return parse_intent_with_source(text, llm_enabled=llm_enabled, llm_api_key=llm_api_key).intent
