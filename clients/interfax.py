# ✅ clients/interfax.py
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

    async def search_reports_by_category(
        self, subject_code: str, category_name: str, year: int, count: int = 100
    ) -> list[dict]:
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
        Скачивает файл через publicUrl и, если это ZIP — распаковывает.
        Возвращает список путей к PDF-файлам.
        """
        public_url = file_data.get("publicUrl")
        file_name = file_data.get("type", {}).get("name", "report").replace(" ", "_")
        uid = file_data.get("uid", "")[:6]
        base_name = f"{file_name}_{uid}"

        async with httpx.AsyncClient(timeout=60) as client:
            resp = await client.get(public_url, headers={"User-Agent": "Mozilla/5.0"}, follow_redirects=True)
            resp.raise_for_status()
            content_type = resp.headers.get("Content-Type", "").lower()

            suffix = ".zip" if "zip" in content_type or "octet-stream" in content_type else ".pdf"
            bin_path = os.path.join(tempfile.gettempdir(), base_name + suffix)

            with open(bin_path, "wb") as f:
                f.write(resp.content)

            logger.info(f"📥 Файл скачан: {bin_path}")

            if suffix == ".pdf":
                return [bin_path]

            # ZIP-архив: распаковка
            zip_path = bin_path
            extracted_dir = os.path.join(tempfile.gettempdir(), f"unzipped_{uid}")
            os.makedirs(extracted_dir, exist_ok=True)

            with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                zip_ref.extractall(extracted_dir)

            pdfs = [
                os.path.join(extracted_dir, name)
                for name in zip_ref.namelist()
                if name.lower().endswith(".pdf")
            ]
            return pdfs

    async def close(self):
        await self._client.aclose()
