# bot/services/scheduler.py

import asyncio
from aiogram import Bot
from clients.interfax_client import interfax_client
from services.dispatcher import process_events

async def periodic_worker(bot: Bot, interval: int):
    while True:
        await process_events(bot, interfax_client)
        await asyncio.sleep(interval * 60)
