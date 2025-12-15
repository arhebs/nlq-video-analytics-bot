"""aiogram message handlers.

Hard contract: every incoming message must produce exactly one integer reply (digits only, optional
leading '-'). On any unsupported input or internal error, reply `0` and log internally.
"""

from __future__ import annotations

import logging
import re
from time import monotonic

from aiogram.types import Message

from src.app import App
from src.db.pool import get_conn
from src.db.query import fetch_scalar_int
from src.intent.parser import IntentParserError, parse_intent_with_source
from src.sql.builder import SQLBuilderError, build_query

logger = logging.getLogger(__name__)
_INTEGER_REPLY_RE = re.compile(r"^-?\d+$")


def _is_command_text(text: str) -> bool:
    return text.lstrip().startswith("/")


def _sanitize_reply(text: str) -> str:
    """Return a safe digits-only reply string (fallback to `0`)."""

    value = (text or "").strip()
    if _INTEGER_REPLY_RE.fullmatch(value):
        return value
    return "0"


async def handle_message(message: Message, app: App) -> None:
    """Handle any incoming Telegram message and reply with exactly one integer string."""

    started = monotonic()
    result_text = "0"

    # noinspection PyBroadException
    try:
        raw_text = (message.text or message.caption or "")
        if not raw_text.strip() or _is_command_text(raw_text):
            await message.answer("0")
            return

        parse_result = parse_intent_with_source(
            raw_text,
            llm_enabled=app.settings.llm_enabled,
            llm_api_key=app.settings.llm_api_key,
        )
        sql, params = build_query(parse_result.intent)

        async with get_conn(app.pool) as conn:
            value = await fetch_scalar_int(conn, sql, params)

        result_text = str(value)

        latency_ms = int((monotonic() - started) * 1000)
        logger.info(
            "handled source=%s operation=%s metric=%s latency_ms=%d",
            parse_result.source,
            parse_result.intent.operation,
            parse_result.intent.metric,
            latency_ms,
        )
    except (IntentParserError, SQLBuilderError) as exc:
        # Unsupported/unparseable input -> 0 (no stack trace needed).
        latency_ms = int((monotonic() - started) * 1000)
        logger.info("unsupported reason=%s latency_ms=%d", exc, latency_ms)
    except Exception:
        # Handler boundary: any internal error must result in a numeric reply ("0"),
        # without leaking details.
        logger.exception("handler failed")

    await message.answer(_sanitize_reply(result_text))
