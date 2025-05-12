from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton


def main_menu(is_subscribed: bool) -> InlineKeyboardMarkup:
    buttons = [
        [InlineKeyboardButton(text="ℹ️ О боте", callback_data="about_bot")],
        [
            InlineKeyboardButton(
                text="❌ Отписаться" if is_subscribed else "✅ Подписаться",
                callback_data="unsubscribe" if is_subscribed else "subscribe",
            )
        ],
        [
            InlineKeyboardButton(text="📄 Пользовательское соглашение", callback_data="terms")
        ],
        [
            InlineKeyboardButton(text="📂 Найти отчёт", callback_data="search_reports")
        ],
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)
