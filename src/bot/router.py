"""Bot router composition."""

from __future__ import annotations

from aiogram import Router

from src.bot.handlers import handle_message

router = Router(name="root")
router.message.register(handle_message)
