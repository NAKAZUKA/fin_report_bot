import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).parent.parent / "data" / "bot.db"
DB_PATH.parent.mkdir(parents=True, exist_ok=True)

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    with get_db() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                full_name TEXT,
                is_subscribed BOOLEAN NOT NULL DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS reports (
                event_uid TEXT PRIMARY KEY,
                company_name TEXT,
                inn TEXT,
                report_type TEXT,
                report_date TEXT,
                description TEXT,
                document_url_in_minio TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS processed_events (
                event_uid TEXT PRIMARY KEY
            );
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS messages (
                event_uid TEXT PRIMARY KEY,
                company_name TEXT,
                inn TEXT,
                message_type TEXT,
                message_date TEXT,
                message_text TEXT,
                message_url TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            """
        )

def has_event_been_processed(event_uid: str) -> bool:
    with get_db() as conn:
        res = conn.execute("SELECT 1 FROM processed_events WHERE event_uid = ?", (event_uid,)).fetchone()
        return res is not None

def mark_event_as_processed(event_uid: str):
    with get_db() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO processed_events (event_uid) VALUES (?)",
            (event_uid,)
        )

def save_report(
    event_uid: str,
    company_name: str,
    inn: str,
    report_type: str,
    report_date: str,
    description: str,
    document_url_in_minio: str
):
    with get_db() as conn:
        conn.execute(
            """
            INSERT OR IGNORE INTO reports (
                event_uid, company_name, inn, report_type,
                report_date, description, document_url_in_minio
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                event_uid,
                company_name,
                inn,
                report_type,
                report_date,
                description,
                document_url_in_minio
            )
        )

def save_message(
    event_uid: str,
    company_name: str,
    inn: str,
    message_type: str,
    message_date: str,
    message_text: str,
    message_url: str
):
    with get_db() as conn:
        conn.execute(
            """
            INSERT OR IGNORE INTO messages (
                event_uid, company_name, inn,
                message_type, message_date, message_text, message_url
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                event_uid,
                company_name,
                inn,
                message_type,
                message_date,
                message_text,
                message_url
            )
        )
