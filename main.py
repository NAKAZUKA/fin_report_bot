import asyncio
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.fsm.storage.memory import MemoryStorage

from config import load_config
from handlers import start, search
from utils.logging import logger
from db import init_db
from services.dispatcher import process_events
from clients.interfax_client import interfax_client
from aiogram.fsm.storage.memory import MemoryStorage

async def periodic_worker(bot: Bot, interval: int):
    while True:
        await process_events(bot, interfax_client)
        await asyncio.sleep(interval * 60)

async def main():
    init_db()
    config = load_config()
    bot = Bot(token=config.token, default=DefaultBotProperties(parse_mode="HTML"))
    dp = Dispatcher(storage=MemoryStorage())

    dp.include_router(start.router)
    dp.include_router(search.router)

    logger.info("🚀 Bot is starting...")
    await bot.delete_webhook(drop_pending_updates=True)

    # первая проверка
    await process_events(bot, interfax_client)

    # далее проверка по расписанию
    asyncio.create_task(periodic_worker(bot, config.interval_minutes))

    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
