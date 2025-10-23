import asyncio
import httpx
import os
import tempfile
import zipfile
from datetime import datetime
from typing import Optional
from pydantic import BaseModel
from loguru import logger

from utils.token_storage import (
    load_token_from_file,
    save_token_to_file,
    is_token_expired,
)
from db import has_event_been_processed

try:
    import py7zr
    _has_7z = True
except ImportError:
    _has_7z = False


class TokenResponse(BaseModel):
    token: str
    expirationDate: Optional[datetime]


class InterfaxClient:
    BASE_URL = "https://gateway.e-disclosure.ru/api/v1"

    def __init__(self, login: str, password: str):
        self._login = login
        self._password = password
        self._client = httpx.AsyncClient(timeout=60.0)
        self._token: Optional[str] = None
        self._semaphore = asyncio.Semaphore(5)  # максимум 5 запросов одновременно

    async def init(self):
        self._token = await self.get_token()

    async def _limited_request(self, coro):
        async with self._semaphore:
            await asyncio.sleep(0.2)  # 5 запросов в секунду
            return await coro

    async def _authorize(self) -> str:
        logger.info("🔐 Авторизация в Интерфакс API...")
        response = await self._limited_request(self._client.post(
            f"{self.BASE_URL}/auth",
            json={"login": self._login, "password": self._password}
        ))
        response.raise_for_status()
        data = TokenResponse.model_validate(response.json())
        save_token_to_file(data.token, data.expirationDate.isoformat())
        self._token = data.token
        logger.success(f"✅ Токен получен. Действует до {data.expirationDate}")
        return self._token

    async def get_token(self) -> str:
        token, exp_str = load_token_from_file()
        if not token or is_token_expired(exp_str):
            return await self._authorize()
        self._token = token
        return self._token

    async def get_file_events(self, subject_code: str, count: int = 100) -> list[dict]:
        token = await self.get_token()
        headers = {"APIKey": token}
        params = {
            "entity": "Files",
            "subjectCode": [subject_code],
            "count": count
        }
        response = await self._limited_request(self._client.get(
            f"{self.BASE_URL}/disclosure/events", headers=headers, params=params
        ))
        response.raise_for_status()
        events = response.json()

        today = datetime.utcnow().date()
        filtered = []
        for event in events:
            if has_event_been_processed(event["uid"]):
                continue

            file = event.get("file")
            if not file or not file.get("publicUrl"):
                continue

            attrs = {a["name"]: a["value"] for a in file.get("attributes", [])}
            file["attributes"] = attrs

            pub_date_str = attrs.get("DatePub")
            if not pub_date_str:
                continue

            try:
                pub_date = datetime.strptime(pub_date_str, "%d.%m.%Y").date()
            except ValueError:
                continue

            if pub_date == today:
                filtered.append(event)

        return filtered

    async def probe_company_info(self, subject_code: str) -> Optional[dict]:
        token = await self.get_token()
        headers = {"APIKey": token}
        params = {"entity": "Files", "subjectCode": [subject_code], "count": 1}

        response = await self._limited_request(self._client.get(
            f"{self.BASE_URL}/disclosure/events", headers=headers, params=params
        ))
        response.raise_for_status()
        events = response.json()

        for event in events:
            subject = event.get("subject")
            if subject:
                return subject
        return None

    async def search_reports_by_category(
        self, subject_code: str, category_name: str, year: int, count: int = 100
    ) -> list[dict]:
        token = await self.get_token()
        headers = {"APIKey": token}
        params = {"entity": "Files", "subjectCode": [subject_code], "count": count}

        response = await self._limited_request(self._client.get(
            f"{self.BASE_URL}/disclosure/events", headers=headers, params=params
        ))
        response.raise_for_status()
        events = response.json()

        results = []
        for event in events:
            file = event.get("file", {})
            if not file or not file.get("publicUrl"):
                continue

            category = file.get("category", {}).get("name", "").lower()
            if category_name.lower() not in category:
                continue

            attrs = {a["name"]: a["value"] for a in file.get("attributes", [])}
            file["attributes"] = attrs

            if str(year) != attrs.get("YearRep", ""):
                continue

            results.append(event)

        return results

    async def download_and_extract_file(self, file_data: dict) -> list[str]:
        """
        Скачивает файл по publicUrl. Поддерживает:
        - PDF
        - ZIP, 7Z (если установлен py7zr)
        - HTML → пропуск
        Возвращает список файлов.
        """
        public_url = file_data.get("publicUrl")
        file_name = file_data.get("type", {}).get("name", "report").replace(" ", "_")
        uid = file_data.get("uid", "")[:6]
        base_name = f"{file_name}_{uid}"

        try:
            response = await self._limited_request(httpx.AsyncClient(timeout=60).get(
                public_url, headers={"User-Agent": "Mozilla/5.0"}, follow_redirects=True
            ))

            response.raise_for_status()
            content = response.content
            content_type = response.headers.get("Content-Type", "").lower()

            if content[:15].lower().startswith(b'<!doctype html') or b'<html' in content[:200].lower():
                logger.warning(f"⚠️ Вместо файла получен HTML: {public_url}")
                return []

            # Определяем расширение
            if b'%pdf' in content[:1024]:
                suffix = ".pdf"
            elif b'7z' in content[:8]:
                suffix = ".7z"
            elif b'pk' in content[:4].lower() or "zip" in content_type:
                suffix = ".zip"
            else:
                suffix = ".bin"

            bin_path = os.path.join(tempfile.gettempdir(), base_name + suffix)
            with open(bin_path, "wb") as f:
                f.write(content)

            logger.info(f"📥 Файл скачан: {bin_path}")

            if suffix == ".pdf":
                return [bin_path]

            extracted_dir = os.path.join(tempfile.gettempdir(), f"unzipped_{uid}")
            os.makedirs(extracted_dir, exist_ok=True)

            if suffix == ".zip":
                with zipfile.ZipFile(bin_path, 'r') as zip_ref:
                    zip_ref.extractall(extracted_dir)
            elif suffix == ".7z" and _has_7z:
                with py7zr.SevenZipFile(bin_path, mode='r') as archive:
                    archive.extractall(path=extracted_dir)
            else:
                logger.warning(f"⚠️ Расширение {suffix} не поддерживается.")
                return []

            extracted_files = [
                os.path.join(root, file)
                for root, _, files in os.walk(extracted_dir)
                for file in files
            ]

            if not extracted_files:
                logger.warning(f"⚠️ В архиве {bin_path} нет файлов.")

            return extracted_files

        except httpx.HTTPError as e:
            logger.error(f"❌ HTTP ошибка при скачивании: {e}")
            return []
        except Exception as e:
            logger.error(f"❌ Общая ошибка при скачивании: {e}")
            return []

    async def close(self):
        await self._client.aclose()
