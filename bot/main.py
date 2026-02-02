from __future__ import annotations

import asyncio
import logging
from urllib.parse import urlsplit

from aiohttp import web
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application
from dotenv import load_dotenv

from config import Config, build_config
from handlers import router, set_service
from notify_server import start_internal_server
from service import BotService


load_dotenv()


async def run_polling(bot: Bot, dp: Dispatcher) -> None:
    await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())


async def run_webhook(bot: Bot, dp: Dispatcher, config: Config) -> None:
    assert config.webhook_url
    path = urlsplit(config.webhook_url).path or "/webhook"
    app = web.Application()
    SimpleRequestHandler(dp, bot).register(app, path=path)
    setup_application(app, dp, bot=bot)

    await bot.set_webhook(config.webhook_url)

    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, host=config.webhook_host, port=config.webhook_port)
    await site.start()
    logging.info(
        "Webhook running at %s (listen on %s:%s)",
        config.webhook_url,
        config.webhook_host,
        config.webhook_port,
    )

    stop_event = asyncio.Event()
    try:
        await stop_event.wait()
    finally:
        await bot.delete_webhook()
        await runner.cleanup()


async def main() -> None:
    config = build_config()
    logging.basicConfig(
        level=config.log_level, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
    )

    bot = Bot(config.bot_token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = Dispatcher()
    dp.include_router(router)

    service = BotService(config)
    set_service(service)
    await service.start()
    internal_runner = await start_internal_server(bot, config)

    try:
        if config.webhook_url:
            await run_webhook(bot, dp, config)
        else:
            await run_polling(bot, dp)
    except asyncio.CancelledError:
        pass
    finally:
        await internal_runner.cleanup()
        await service.close()
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
