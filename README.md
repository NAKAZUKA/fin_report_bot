
# Telegram Bot for Financial Disclosure Monitoring (Interfax + MinIO)

## 📌 Описание

Данный проект представляет собой Telegram-бота, который автоматически проверяет наличие новых отчетов по заданным компаниям через API Интерфакса, сохраняет их в MinIO-хранилище, ведёт учёт в локальной базе данных и отправляет уведомления подписчикам в Telegram.

---

## 📁 Структура проекта

```
.
├── bot
│   ├── clients/
│   ├── config.py
│   ├── db.py
│   ├── docker-compose.yml
│   ├── Dockerfile
│   ├── handlers/
│   ├── keyboards/
│   ├── main.py
│   ├── pyproject.toml
│   ├── README.md
│   ├── services/
│   └── utils/
├── data/
│   ├── bot.db
│   ├── companies.json
│   └── interfax_token.json
```

---

## 🧰 Установка и запуск

### ⚙️ Требования

- Python 3.12+
- [uv](https://github.com/astral-sh/uv) — менеджер пакетов
- Docker + Docker Compose

### Установка зависимостей

```bash
cd bot/
uv venv
uv pip install -r pyproject.toml
```

---

### 🚀 Запуск

#### Вариант 1: локально

```bash
docker compose up -d minio
cd bot/
uv run python main.py
```

#### Вариант 2: через Docker

```bash
docker compose up --build -d
```

---

## ⚙️ Переменные окружения

Файл `.env`:

```
BOT_TOKEN=
INTERFAX_LOGIN=
INTERFAX_PASSWORD=
DISPATCH_INTERVAL_MINUTES=15
MINIO_ENDPOINT=localhost:9000
MINIO_ACCESS_KEY=minioadmin
MINIO_SECRET_KEY=minioadmin
MINIO_BUCKET=reports
```

> `.env` и `interfax_token.json` не добавляются в git.

---

## 📁 Папка `data/`

Пример `companies.json`:

```json
{
  "ПАО \"Корпоративный Центр ИКС 5\"": "9722079341",
  "МКПАО \"Т-ТЕХНОЛОГИИ\"": "2540283195"
}
```

---

## 📦 Docker Compose команды

```bash
docker compose up -d minio
docker compose down
docker compose logs -f minio
```

---

## 🧠 Функциональность

- FSM-поиск по компании, категории, году
- Хранение отчётов в MinIO
- Подписка пользователей
- SQLite база: `users`, `reports`, `messages`

---

## 🖥 Сервер

Доступ:

```bash
ssh root@109.172.31.67
```

Размещение: [firstvds.ru](https://my.firstvds.ru)

---

## 🔒 Приватные файлы

- `.env`
- `data/interfax_token.json`
- `data/bot.db`

---

## 🚀 Возможности для доработки

- Расширение фильтров (по периоду)
- Поддержка вложений сообщений
- Хранение в PostgreSQL
- Web-интерфейс администратора
