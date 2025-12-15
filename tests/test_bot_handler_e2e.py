"""Tests for the aiogram message handler output contract.

The project contract requires that every incoming message results in exactly one integer reply
(`^-?\\d+$`) with no extra whitespace or punctuation. Any unsupported input must return `0`.
"""

from __future__ import annotations

import re
from contextlib import asynccontextmanager
from types import SimpleNamespace
from typing import Any

import pytest

from src.bot.handlers import handle_message

_INTEGER_RE = re.compile(r"-?\d+")


class _FakeMessage:
    def __init__(self, text: str | None) -> None:
        self.text = text
        self.answers: list[str] = []

    async def answer(self, text: str) -> None:
        """Record the outgoing bot reply (aiogram's `Message.answer` substitute)."""
        self.answers.append(text)


def _make_app() -> Any:
    return SimpleNamespace(
        settings=SimpleNamespace(llm_enabled=False, llm_api_key=None),
        pool=object(),
    )


def _assert_single_integer_reply(message: _FakeMessage) -> None:
    assert message.answers and len(message.answers) == 1
    assert _INTEGER_RE.fullmatch(message.answers[0]) is not None


@pytest.mark.asyncio
async def test_handler_replies_zero_for_empty_text() -> None:
    app = _make_app()
    message = _FakeMessage(text=None)

    await handle_message(message, app)  # type: ignore[arg-type]

    assert message.answers == ["0"]
    _assert_single_integer_reply(message)


@pytest.mark.asyncio
async def test_handler_replies_zero_for_command() -> None:
    app = _make_app()
    message = _FakeMessage(text="/start")

    await handle_message(message, app)  # type: ignore[arg-type]

    assert message.answers == ["0"]
    _assert_single_integer_reply(message)


@pytest.mark.asyncio
async def test_handler_replies_zero_for_ambiguous_metric() -> None:
    app = _make_app()
    message = _FakeMessage(text="Сколько реакций у видео?")

    await handle_message(message, app)  # type: ignore[arg-type]

    assert message.answers == ["0"]
    _assert_single_integer_reply(message)


@pytest.mark.asyncio
async def test_handler_replies_digits_only_on_success(monkeypatch: pytest.MonkeyPatch) -> None:
    app = _make_app()
    message = _FakeMessage(text="Сколько всего видео есть в системе?")

    @asynccontextmanager
    async def _fake_get_conn(_pool: Any):
        yield object()

    async def _fake_fetch_scalar_int(_conn: Any, _sql: str, _params: tuple[Any, ...] = ()) -> int:
        return 123

    monkeypatch.setattr(
        "src.bot.handlers.parse_intent_with_source",
        lambda *_args, **_kwargs: SimpleNamespace(intent=object(), source="rules"),
    )
    monkeypatch.setattr("src.bot.handlers.build_query", lambda _intent: ("SELECT 1", ()))
    monkeypatch.setattr("src.bot.handlers.get_conn", _fake_get_conn)
    monkeypatch.setattr("src.bot.handlers.fetch_scalar_int", _fake_fetch_scalar_int)

    await handle_message(message, app)  # type: ignore[arg-type]

    assert message.answers == ["123"]
    _assert_single_integer_reply(message)
