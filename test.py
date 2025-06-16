import asyncio
import httpx
import os

TOKEN = "13e0c4a1bd214dd4895270eceae1a8b8"
BASE_URL = "https://gateway.e-disclosure.ru/api/v1"
HEADERS = {"APIKey": TOKEN, "User-Agent": "Mozilla/5.0"}
CHUNK_SIZE = 10_000_000


async def fetch_latest_reports(count: int = 10) -> list[dict]:
    async with httpx.AsyncClient(timeout=30) as client:
        params = {"entity": "Files", "count": count}
        resp = await client.get(f"{BASE_URL}/disclosure/events", headers=HEADERS, params=params)
        resp.raise_for_status()
        return resp.json()


async def download_by_public_url(public_url: str, filename: str) -> bool:
    async with httpx.AsyncClient(timeout=60) as client:
        print(f"🌐 Пробуем publicUrl: {public_url}")
        resp = await client.get(public_url, headers={"User-Agent": "Mozilla/5.0"}, follow_redirects=True)
        resp.raise_for_status()
        content_type = resp.headers.get("Content-Type", "").lower()
        print(f"📎 Content-Type: {content_type}")

        ext = ".pdf" if "pdf" in content_type else ".bin"
        final_name = filename + ext
        with open(final_name, "wb") as f:
            f.write(resp.content)
        print(f"✅ Сохранён файл: {final_name}")
        return True


async def main():
    print("🔄 Получаем события...")
    events = await fetch_latest_reports()
    for ev in events:
        file = ev.get("file")
        if not file:
            continue
        uid = file.get("uid")
        public_url = file.get("publicUrl")
        name = file.get("type", {}).get("name", "doc").replace(" ", "_")
        filename = f"{name}_{uid[:6]}"
        if public_url:
            await download_by_public_url(public_url, filename)
            break


if __name__ == "__main__":
    asyncio.run(main())
