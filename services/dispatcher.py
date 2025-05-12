# services/dispatcher.py

import json
from pathlib import Path
from aiogram import Bot
from aiogram.types import FSInputFile
from loguru import logger
from clients.interfax_client import interfax_client
from utils.minio_client import upload_file
from db import mark_event_as_processed, save_report, save_message, get_db
import aiofiles
from datetime import datetime

COMPANIES_PATH = Path(__file__).parent.parent.parent / "data" / "companies.json"
with open(COMPANIES_PATH, "r", encoding="utf-8") as f:
    COMPANIES = json.load(f)

async def process_events(bot: Bot, interfax_client):
    logger.info("🔁 Начинаю проверку новых событий через Интерфакс...")

    for company_name, inn in COMPANIES.items():
        logger.info(f"🔍 Проверка компании: {company_name} (ИНН: {inn})")

        # === 📄 ОТЧЁТЫ С ФАЙЛАМИ ===
        try:
            file_events = await interfax_client.get_file_events(subject_code=inn)
        except Exception as e:
            logger.error(f"❌ Ошибка при получении отчётов для {company_name}: {e}")
            file_events = []

        for event in file_events:
            try:
                uid = event["uid"]
                file_data = event["file"]
                file_uid = file_data["uid"]
                attrs = file_data.get("attributes", {})

                pub_date = attrs.get("DatePub")
                if not pub_date or datetime.strptime(pub_date, "%d.%m.%Y").date() != datetime.utcnow().date():
                    continue  # фильтрация по дате публикации

                # === Загрузка файла ===
                file_bytes = await interfax_client.download_file(file_uid)
                local_path = Path(f"/tmp/{uid}.pdf")
                async with aiofiles.open(local_path, "wb") as f:
                    await f.write(file_bytes)

                minio_url = upload_file(file_bytes, f"{uid}.pdf")

                report_type = file_data["type"]["name"]
                description = file_data.get("description", "")

                save_report(
                    event_uid=uid,
                    company_name=company_name,
                    inn=inn,
                    report_type=report_type,
                    report_date=pub_date,
                    description=description,
                    document_url_in_minio=minio_url
                )
                mark_event_as_processed(uid)

                caption = (
                    f"🏢 <b>{company_name}</b>\n"
                    f"📄 Тип: <b>{report_type}</b>\n"
                    f"📅 Год: <b>{attrs.get('YearRep', 'не указано')}</b>\n"
                    f"🗓 Дата публикации: <b>{pub_date}</b>\n"
                    f"📝 {description or 'Описание отсутствует'}"
                )

                doc = FSInputFile(path=local_path, filename=f"{uid}.pdf")

                with get_db() as conn:
                    subs = conn.execute("SELECT user_id FROM users WHERE is_subscribed = 1").fetchall()
                    for user in subs:
                        await bot.send_document(
                            chat_id=user["user_id"],
                            document=doc,
                            caption=caption,
                            parse_mode="HTML"
                        )

                logger.success(f"📤 Отчёт {uid} отправлен подписчикам.")
            except Exception as e:
                logger.error(f"❌ Ошибка при обработке отчёта {event.get('uid')} компании {company_name}: {e}")

        # === 📰 СООБЩЕНИЯ (новости) ===
        try:
            message_events = await interfax_client.get_message_events(subject_code=inn)
        except Exception as e:
            logger.error(f"❌ Ошибка при получении сообщений для {company_name}: {e}")
            message_events = []

        for event in message_events:
            try:
                uid = event["uid"]
                message_data = event["message"]
                pub_date = event.get("date")
                if not pub_date or datetime.fromisoformat(pub_date).date() != datetime.utcnow().date():
                    continue  # только свежие сообщения

                title = message_data.get("header") or message_data.get("type", {}).get("name")
                text = message_data.get("text", "")
                url = message_data.get("publicUrl")

                save_message(
                    event_uid=uid,
                    company_name=company_name,
                    inn=inn,
                    message_type=title,
                    message_date=pub_date,
                    message_text=text,
                    message_url=url
                )
                mark_event_as_processed(uid)

                message_text = (
                    f"🏢 <b>{company_name}</b>\n"
                    f"📌 <b>{title}</b>\n"
                    f"📅 <b>{datetime.fromisoformat(pub_date).strftime('%d.%m.%Y')}</b>\n"
                    f"🔗 <a href=\"{url}\">Открыть публикацию</a>"
                )

                with get_db() as conn:
                    subs = conn.execute("SELECT user_id FROM users WHERE is_subscribed = 1").fetchall()
                    for user in subs:
                        await bot.send_message(
                            chat_id=user["user_id"],
                            text=message_text,
                            parse_mode="HTML",
                            disable_web_page_preview=False
                        )

                logger.success(f"📰 Сообщение {uid} отправлено.")
            except Exception as e:
                logger.error(f"❌ Ошибка при обработке сообщения {event.get('uid')} компании {company_name}: {e}")

    logger.info("✅ Проверка завершена.")
