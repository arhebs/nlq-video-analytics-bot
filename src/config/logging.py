"""Logging configuration for the bot service."""

from __future__ import annotations

import logging
import os


def configure_logging(level: str | None = None) -> None:
    """Configure Python logging for the process.

    Logs are intended for internal diagnostics only and must never be sent back to the Telegram user.
    """

    log_level = (level or os.getenv("LOG_LEVEL") or "INFO").upper()
    logging.basicConfig(
        level=log_level,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )

    # Reduce noisy third-party logs by default.
    logging.getLogger("aiogram.event").setLevel(logging.WARNING)

