from aiogram import Bot
from loguru import logger
from clients.interfax_client import interfax_client
from db import (
    get_db,
    mark_event_as_processed,
    save_report,
)
from datetime import datetime

async def process_events(bot: Bot, interfax_client):
    logger.info("🔁 Начинаю проверку новых событий через Интерфакс...")

    with get_db() as conn:
        rows = conn.execute("""
            SELECT u.user_id, u.full_name, c.company_name, c.inn
            FROM users u
            JOIN user_companies c ON u.user_id = c.user_id
            WHERE u.is_subscribed = 1
        """).fetchall()

    user_companies = {}
    for row in rows:
        user_companies.setdefault((row["user_id"], row["full_name"]), []).append((row["company_name"], row["inn"]))

    for (user_id, full_name), companies in user_companies.items():
        for company_name, inn in companies:
            logger.info(f"🔍 [{user_id}] {full_name} — {company_name} (ИНН: {inn})")

            try:
                file_events = await interfax_client.get_file_events(subject_code=inn)
            except Exception as e:
                logger.error(f"❌ Ошибка при получении отчётов для {company_name}: {e}")
                continue

            for event in file_events:
                try:
                    uid = event["uid"]
                    file_data = event["file"]
                    attrs = file_data.get("attributes", {})
                    public_url = file_data.get("publicUrl")

                    pub_date = attrs.get("DatePub")
                    if not pub_date or datetime.strptime(pub_date, "%d.%m.%Y").date() != datetime.utcnow().date():
                        continue

                    report_type = file_data["type"]["name"]
                    description = file_data.get("description", "")

                    save_report(
                        event_uid=uid,
                        company_name=company_name,
                        inn=inn,
                        report_type=report_type,
                        report_date=pub_date,
                        description=description,
                        document_url_in_minio=public_url
                    )
                    mark_event_as_processed(uid)

                    caption = (
                        f"🏢 <b>{company_name}</b>\n"
                        f"📄 Тип: <b>{report_type}</b>\n"
                        f"🗓 Год: <b>{attrs.get('YearRep', 'не указано')}</b>\n"
                        f"🗓 Дата публикации: <b>{pub_date}</b>\n"
                        f"📜 {description or 'Описание отсутствует'}\n"
                        f"🔗 <a href=\"{public_url}\">Скачать отчёт</a>"
                    )

                    await bot.send_message(
                        chat_id=user_id,
                        text=caption,
                        parse_mode="HTML"
                    )

                    logger.success(f"📤 Отчёт {uid} отправлен пользователю {user_id}.")
                except Exception as e:
                    logger.error(f"❌ Ошибка при обработке отчёта {event.get('uid')} для {company_name}: {e}")

    logger.info("✅ Фоновая проверка завершена.")
