import asyncio
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.fsm.storage.memory import MemoryStorage

from config import load_config
from handlers import start, search, companies
from utils.logging import logger
from db import init_db
from services.scheduler import periodic_worker
from services.dispatcher import process_events
from clients.interfax_client import interfax_client

async def main():
    init_db()
    config = load_config()
    bot = Bot(token=config.token, default=DefaultBotProperties(parse_mode="HTML"))
    dp = Dispatcher(storage=MemoryStorage())

    dp.include_router(start.router)
    dp.include_router(search.router)
    dp.include_router(companies.router)

    logger.info("🚀 Bot is starting...")
    await bot.delete_webhook(drop_pending_updates=True)

    # первая проверка
    await interfax_client.init()
    await process_events(bot, interfax_client)

    # далее проверка по расписанию
    asyncio.create_task(periodic_worker(bot, config.interval_minutes))

    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
