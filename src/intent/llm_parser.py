"""Optional LLM-based intent parser (feature-flagged).

The LLM is only allowed to produce **Intent JSON**. The output must be validated against the schema
and must never contain executable SQL.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


class LLMParserError(RuntimeError):
    """Raised when the LLM parser fails to return valid JSON."""


@dataclass(frozen=True)
class LLMConfig:
    """Configuration for the OpenAI-style Chat Completions API call."""

    api_key: str
    model: str = "gpt-4o-mini"
    api_base: str = "https://api.openai.com/v1"
    timeout_s: float = 30.0


def _load_prompt() -> str:
    prompt_path = Path(__file__).resolve().parent / "prompt_intent_v1.md"
    return prompt_path.read_text(encoding="utf-8")


def _strip_code_fences(text: str) -> str:
    value = (text or "").strip()
    if value.startswith("```"):
        value = value.strip("`")
        # After stripping backticks, try to remove leading "json" marker.
        value = value.removeprefix("json").strip()
    return value


def _chat_completions_url(api_base: str) -> str:
    return api_base.rstrip("/") + "/chat/completions"


def parse_intent_json_via_llm(user_text: str, *, config: LLMConfig) -> dict[str, Any]:
    """Call an LLM and return the parsed JSON object.

    The call is compatible with OpenAI-style `/v1/chat/completions` APIs.
    """

    prompt = _load_prompt()

    payload = {
        "model": config.model,
        "temperature": 0,
        "messages": [
            {"role": "system", "content": prompt},
            {"role": "user", "content": user_text},
        ],
    }

    req = Request(
        _chat_completions_url(config.api_base),
        method="POST",
        headers={
            "Authorization": f"Bearer {config.api_key}",
            "Content-Type": "application/json",
        },
        data=json.dumps(payload).encode(),
    )

    try:
        with urlopen(req, timeout=config.timeout_s) as resp:  # noqa: S310 (explicit, feature-flagged network call)
            body = resp.read()
    except HTTPError as exc:
        raise LLMParserError(f"LLM HTTP error: {exc.code}") from exc
    except URLError as exc:
        raise LLMParserError("LLM connection error") from exc

    try:
        decoded = json.loads(body)
        content = decoded["choices"][0]["message"]["content"]
    except Exception as exc:  # noqa: BLE001
        raise LLMParserError("Unexpected LLM response format") from exc

    try:
        return json.loads(_strip_code_fences(content))
    except json.JSONDecodeError as exc:
        raise LLMParserError("LLM did not return valid JSON") from exc


def llm_config_from_env(*, api_key: str | None = None) -> LLMConfig:
    """Build LLM config from environment variables.

    Environment variables (optional):
        - LLM_MODEL
        - LLM_API_BASE
        - LLM_TIMEOUT_S
    """

    key = api_key or os.getenv("LLM_API_KEY") or ""
    if not key:
        raise LLMParserError("LLM_API_KEY is required")

    timeout_s = float(os.getenv("LLM_TIMEOUT_S") or "30")
    return LLMConfig(
        api_key=key,
        model=os.getenv("LLM_MODEL") or "gpt-4o-mini",
        api_base=os.getenv("LLM_API_BASE") or "https://api.openai.com/v1",
        timeout_s=timeout_s,
    )
