import httpx
from datetime import datetime
from typing import Optional
from pydantic import BaseModel
from loguru import logger
from utils.token_storage import load_token_from_file, save_token_to_file, is_token_expired
from db import has_event_been_processed

class TokenResponse(BaseModel):
    token: str
    expirationDate: Optional[datetime]

class InterfaxClient:
    BASE_URL = "https://gateway.e-disclosure.ru/api/v1"

    def __init__(self, login: str, password: str):
        self._login = login
        self._password = password
        self._client = httpx.AsyncClient(timeout=15.0)

    async def _authorize(self):
        logger.info("🔐 Авторизация в Интерфакс API...")
        response = await self._client.post(f"{self.BASE_URL}/auth", json={
            "login": self._login,
            "password": self._password
        })
        response.raise_for_status()
        data = TokenResponse.model_validate(response.json())
        save_token_to_file(data.token, data.expirationDate.isoformat())
        logger.success(f"✅ Токен получен. Действует до {data.expirationDate}")
        return data.token

    async def get_token(self) -> str:
        token, exp_str = load_token_from_file()
        if not token or is_token_expired(exp_str):
            return await self._authorize()
        return token

    async def get_file_events(self, subject_code: str, count: int = 100) -> list[dict]:
        """
        Получить только события, связанные с отчетами (файлами) для выбранной компании
        """
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

        today = datetime.utcnow().date()
        filtered = []
        for event in events:
            if has_event_been_processed(event["uid"]):
                continue
            file = event.get("file")
            if not file or not file.get("publicUrl"):
                continue

            # Атрибуты файла в словарь
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

    async def get_message_events(self, subject_code: str, count: int = 100) -> list[dict]:
        """
        Получить события для сообщений (не для отчетов)
        """
        token = await self.get_token()
        headers = {"APIKey": token}
        params = {
            "entity": "Messages",
            "subjectCode": [subject_code],
            "count": count
        }
        response = await self._client.get(f"{self.BASE_URL}/disclosure/events", headers=headers, params=params)
        response.raise_for_status()
        events = response.json()

        today = datetime.utcnow().date()
        return [
            e for e in events
            if not has_event_been_processed(e["uid"])
            and e.get("message", {}).get("publicUrl")
            and datetime.fromisoformat(e["date"]).date() == today
        ]

    async def get_filtered_reports(self, subject_code: str, file_type: int, year: int, count: int = 100) -> list[dict]:
        """
        Получить отчеты по типу и году для компании
        """
        token = await self.get_token()
        headers = {"APIKey": token}
        params = {
            "entity": "Files",
            "subjectCode": [subject_code],
            "type": [file_type],
            "count": count
        }
        response = await self._client.get(f"{self.BASE_URL}/disclosure/events", headers=headers, params=params)
        response.raise_for_status()

        events = response.json()
        filtered_events = []
        for event in events:
            file = event.get("file", {})
            if not file or not file.get("publicUrl"):
                continue

            attrs = {a["name"]: a["value"] for a in file.get("attributes", [])}
            file["attributes"] = attrs

            # Фильтруем отчеты по году
            if str(year) in attrs.get("YearRep", ""):
                filtered_events.append(event)
        
        return filtered_events

    async def get_file_types(self) -> list[dict]:
        """
        Получить типы отчетности (файлов)
        """
        token = await self.get_token()
        headers = {"APIKey": token}
        response = await self._client.get(f"{self.BASE_URL}/dictionaries/file-types", headers=headers)
        response.raise_for_status()
        return response.json()

    async def download_file(self, file_uid: str) -> bytes:
        """
        Скачать файл по UID
        """
        token = await self.get_token()
        headers = {"APIKey": token}
        response = await self._client.get(f"{self.BASE_URL}/disclosure/download/files/{file_uid}", headers=headers)
        response.raise_for_status()
        return response.content

    async def close(self):
        """
        Закрыть соединение
        """
        await self._client.aclose()
