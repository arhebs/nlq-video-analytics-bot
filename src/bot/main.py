"""Bot process entrypoint."""

from __future__ import annotations

import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties

from src.app import create_app
from src.bot.router import router
from src.config.logging import configure_logging
from src.config.settings import load_settings

logger = logging.getLogger(__name__)


async def main() -> None:
    """Run the Telegram bot polling loop."""

    settings = load_settings()
    configure_logging()

    app = create_app(settings)
    await app.pool.open(wait=True)

    bot = Bot(token=settings.telegram_bot_token, default=DefaultBotProperties(parse_mode=None))
    dp = Dispatcher()
    dp.include_router(router)

    try:
        await dp.start_polling(bot, app=app)
    finally:
        logger.info("shutting down")
        await app.pool.close()


if __name__ == "__main__":
    asyncio.run(main())
