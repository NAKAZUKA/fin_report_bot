from aiogram import Router, types
from aiogram.filters import Command
from aiogram.types import CallbackQuery
from keyboards.main import main_menu
from db import get_db

router = Router()


def is_user_subscribed(user_id: int) -> bool:
    with get_db() as conn:
        res = conn.execute(
            "SELECT is_subscribed FROM users WHERE user_id = ?", (user_id,)
        ).fetchone()
        return bool(res["is_subscribed"]) if res else False


def set_subscription(user_id: int, full_name: str, subscribed: bool):
    with get_db() as conn:
        conn.execute(
            """
            INSERT INTO users (user_id, full_name, is_subscribed)
            VALUES (?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET is_subscribed = excluded.is_subscribed
        """,
            (user_id, full_name, int(subscribed)),
        )


@router.message(Command("start"))
async def start_cmd(message: types.Message):
    is_sub = is_user_subscribed(message.from_user.id)

    text = (
        f"👋 Привет, {message.from_user.full_name}!\n\n"
        "Этот бот присылает отчётность компаний из сервиса Интерфакс.\n\n"
        f"📩 <b>Статус подписки</b>: {'✅ подписаны' if is_sub else '❌ не подписаны'}"
    )

    sent = await message.answer(text, reply_markup=main_menu(is_sub))
    await message.delete()


@router.callback_query(lambda c: c.data in ("subscribe", "unsubscribe"))
async def toggle_subscription(callback: CallbackQuery):
    user_id = callback.from_user.id
    full_name = callback.from_user.full_name
    want_sub = callback.data == "subscribe"

    set_subscription(user_id, full_name, want_sub)

    text = (
        f"✅ Вы {'подписались на' if want_sub else 'отписались от'} рассылку отчётности.\n\n"
        f"📩 <b>Текущий статус</b>: {'✅ подписаны' if want_sub else '❌ не подписаны'}"
    )

    await callback.message.edit_text(text, reply_markup=main_menu(want_sub))
    await callback.answer()


@router.callback_query(lambda c: c.data == "about_bot")
async def about_bot(callback: CallbackQuery):
    is_sub = is_user_subscribed(callback.from_user.id)
    await callback.message.edit_text(
        "ℹ️ <b>О боте</b>\n\n"
        "📊 Этот бот отслеживает публикации финансовой отчётности компаний через API Интерфакса.\n"
        "После подписки ты будешь получать уведомления с документами и датой публикации.",
        reply_markup=main_menu(is_sub),
    )
    await callback.answer()


@router.callback_query(lambda c: c.data == "terms")
async def terms(callback: CallbackQuery):
    is_sub = is_user_subscribed(callback.from_user.id)
    await callback.message.edit_text(
        "📄 <b>Пользовательское соглашение</b>\n\n"
        "Подписываясь на рассылку, вы соглашаетесь получать уведомления "
        "о новых публикациях финансовой отчётности компаний.\n\n"
        "Источник: [Интерфакс – раскрытие информации](https://www.e-disclosure.ru)",
        reply_markup=main_menu(is_sub),
        disable_web_page_preview=True,
    )
    await callback.answer()
