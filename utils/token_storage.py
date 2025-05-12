# bot/utils/token_storage.py
import json
from datetime import datetime
from pathlib import Path

TOKEN_FILE = Path(__file__).parent.parent.parent / "data" / "interfax_token.json"

def load_token_from_file():
    if not TOKEN_FILE.exists():
        return None, None
    with open(TOKEN_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)
        return data.get("token"), data.get("expirationDate")

def save_token_to_file(token: str, expiration_date: str):
    with open(TOKEN_FILE, "w", encoding="utf-8") as f:
        json.dump({
            "token": token,
            "expirationDate": expiration_date
        }, f, ensure_ascii=False, indent=2)

def is_token_expired(expiration_date: str) -> bool:
    if not expiration_date:
        return True
    return datetime.utcnow() >= datetime.fromisoformat(expiration_date)
