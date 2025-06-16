# ✅ clients/interfax.py
import httpx
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


class TokenResponse(BaseModel):
    token: str
    expirationDate: Optional[datetime]


class InterfaxClient:
    BASE_URL = "https://gateway.e-disclosure.ru/api/v1"
    CHUNK_SIZE = 10_000_000

    def __init__(self, login: str, password: str):
        self._login = login
        self._password = password
        self._client = httpx.AsyncClient(timeout=60.0)
        self._token: Optional[str] = None

    async def init(self):
        self._token = await self.get_token()

    async def _authorize(self) -> str:
        logger.info("🔐 Авторизация в Интерфакс API...")
        response = await self._client.post(
            f"{self.BASE_URL}/auth",
            json={"login": self._login, "password": self._password}
        )
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
        response = await self._client.get(
            f"{self.BASE_URL}/disclosure/events", headers=headers, params=params
        )
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

            if pub_date != today:
                continue

            filtered.append(event)
        return filtered

    async def probe_company_info(self, subject_code: str) -> dict | None:
        token = await self.get_token()
        headers = {"APIKey": token}
        params = {
            "entity": "Files",
            "subjectCode": [subject_code],
            "count": 1
        }
        response = await self._client.get(
            f"{self.BASE_URL}/disclosure/events", headers=headers, params=params
        )
        response.raise_for_status()
        events = response.json()

        for event in events:
            subject = event.get("subject")
            if subject:
                return subject
        return None

    async def search_reports_by_category(self, subject_code: str, category_name: str, year: int, count: int = 100) -> list[dict]:
        token = await self.get_token()
        headers = {"APIKey": token}
        params = {
            "entity": "Files",
            "subjectCode": [subject_code],
            "count": count
        }
        response = await self._client.get(f"{self.BASE_URL}/disclosure/events", headers=headers, params=params)
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
    
    async def close(self):
        await self._client.aclose()

    async def download_file(self, file_data: dict) -> bytes:
        """
        Скачивает файл из Интерфакс API либо по UID, либо по publicUrl.
        Отдаёт байтовое содержимое файла, если удалось скачать PDF.
        """
        token = await self.get_token()
        user_agent = {"User-Agent": "Mozilla/5.0"}
        headers = {"APIKey": token, **user_agent}

        file_uid = file_data.get("uid")
        public_url = file_data.get("publicUrl")

        if not file_uid and not public_url:
            raise ValueError("❌ Нет ни UID, ни publicUrl — невозможно скачать файл")

        file_url = f"{self.BASE_URL}/disclosure/download/files/{file_uid}" if file_uid else None

        # 🧪 Пробуем сначала скачать по UID через Range-запросы
        if file_url:
            try:
                head_resp = await self._client.head(file_url, headers=headers)
                if head_resp.status_code == 404:
                    logger.warning("⚠️ Файл по UID не найден, переходим к publicUrl.")
                    raise FileNotFoundError()

                head_resp.raise_for_status()
                total_size = int(head_resp.headers.get("Content-Length", "0"))
                logger.info(f"📦 Размер файла: {total_size} байт")

                chunks = []
                downloaded = 0
                attempt = 1
                while downloaded < total_size:
                    start = downloaded
                    end = min(start + self.CHUNK_SIZE - 1, total_size - 1)
                    range_header = {"Range": f"bytes={start}-{end}"}
                    logger.info(f"📥 Загрузка: bytes={start}-{end}")

                    resp = await self._client.get(file_url, headers={**headers, **range_header})
                    resp.raise_for_status()

                    chunks.append(resp.content)
                    downloaded += len(resp.content)
                    attempt += 1

                full_content = b"".join(chunks)
                if len(full_content) != total_size:
                    logger.warning("⚠️ Итоговый размер не совпадает с Content-Length")
                return full_content

            except Exception as e:
                logger.warning(f"⚠️ Ошибка при загрузке по UID: {e}. Пробуем через publicUrl...")

        # 🔄 Fallback: загрузка через publicUrl
        try:
            resp = await self._client.get(public_url, headers=user_agent, follow_redirects=True)
            resp.raise_for_status()
            content_type = resp.headers.get("Content-Type", "")
            if "application/pdf" not in content_type.lower():
                logger.warning(f"⚠️ Не PDF-файл. Content-Type: {content_type}")
                raise ValueError("Получен не PDF-файл. Публикация могла быть удалена.")
            return resp.content
        except Exception as e:
            logger.error(f"❌ Ошибка при скачивании по publicUrl: {e}")
            raise
