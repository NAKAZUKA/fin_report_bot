# ✅ dispatcher.py

import os
from datetime import datetime

from aiogram import Bot
from aiogram.types import FSInputFile
from loguru import logger

from clients.interfax_client import interfax_client
from db import (
    get_db,
    mark_event_as_processed,
    save_report,
)
from utils.minio_client import upload_file
from utils.cleaner import remove_temp_files


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
                uid = event["uid"]
                file_data = event.get("file", {})
                attrs = file_data.get("attributes", {})
                public_url = file_data.get("publicUrl")

                pub_date = attrs.get("DatePub")
                if not pub_date or datetime.strptime(pub_date, "%d.%m.%Y").date() != datetime.utcnow().date():
                    continue

                report_type = file_data.get("type", {}).get("name", "Отчёт")
                description = file_data.get("description", "") or "Описание отсутствует"

                try:
                    # 🔽 Скачиваем и распаковываем
                    paths = await interfax_client.download_and_extract_file(file_data)
                    if not paths:
                        logger.warning(f"⚠️ Не удалось извлечь файл(ы) для события {uid}")
                        continue

                    for idx, file_path in enumerate(paths):
                        filename = os.path.basename(file_path)
                        with open(file_path, "rb") as f:
                            file_bytes = f.read()

                        # ⬆️ Загрузка в MinIO
                        minio_url = upload_file(file_bytes, filename)

                        # 💾 В БД только один раз
                        if idx == 0:
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

                        # 📤 Отправка пользователю
                        caption = (
                            f"🏢 <b>{company_name}</b>\n"
                            f"📄 Тип: <b>{report_type}</b>\n"
                            f"🗓 Год: <b>{attrs.get('YearRep', 'не указано')}</b>\n"
                            f"🗓 Дата публикации: <b>{pub_date}</b>\n"
                            f"📜 {description}"
                        )

                        doc = FSInputFile(path=file_path)
                        await bot.send_document(
                            chat_id=user_id,
                            document=doc,
                            caption=caption,
                            parse_mode="HTML"
                        )
                        logger.success(f"📤 Файл {filename} отправлен пользователю {user_id}.")

                except Exception as e:
                    logger.error(f"❌ Ошибка при обработке отчёта {uid} для {company_name}: {e}")
                finally:
                    if 'paths' in locals() and paths:
                        remove_temp_files(paths + [os.path.dirname(paths[0])])

    logger.info("✅ Фоновая проверка завершена.")
