from aiogram import Router, F
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

import json
from pathlib import Path

from clients.interfax_client import interfax_client
from keyboards.main import main_menu

router = Router()

COMPANIES_PATH = Path(__file__).parent.parent.parent / "data" / "companies.json"
with open(COMPANIES_PATH, encoding="utf-8") as f:
    COMPANIES: dict[str, str] = json.load(f)

class SearchStates(StatesGroup):
    choosing_company = State()
    choosing_type = State()
    choosing_year = State()
    showing_results = State()

def company_list_keyboard() -> InlineKeyboardMarkup:
    buttons = [
        [InlineKeyboardButton(text=name, callback_data=f"choose_company_{inn}")]
        for name, inn in COMPANIES.items()
    ]
    buttons.append([InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_search")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def type_list_keyboard(types: list[dict], page: int = 0, per_page: int = 20) -> InlineKeyboardMarkup:
    start = page * per_page
    end = start + per_page
    visible = types[start:end]

    buttons = [
        [InlineKeyboardButton(text=t["name"], callback_data=f"choose_type_{t['id']}")]
        for t in visible
    ]

    nav_buttons = []
    if start > 0:
        nav_buttons.append(InlineKeyboardButton(text="⬅️ Назад", callback_data=f"types_page_{page-1}"))
    if end < len(types):
        nav_buttons.append(InlineKeyboardButton(text="➡️ Вперёд", callback_data=f"types_page_{page+1}"))
    if nav_buttons:
        buttons.append(nav_buttons)

    buttons.append([InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_search")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def year_list_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=str(y), callback_data=f"choose_year_{y}")]
        for y in range(2024, 2018, -1)
    ] + [[InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_search")]])

def make_reports_keyboard(events: list[dict], page: int = 0, per_page: int = 5) -> InlineKeyboardMarkup:
    start = page * per_page
    end = start + per_page
    buttons = []

    for e in events[start:end]:
        report_type = e["file"]["type"]["name"]
        pub_date = e["file"]["attributes"].get("DatePub", "??")
        url = e["file"]["publicUrl"]
        buttons.append([
            InlineKeyboardButton(text=f"{report_type} — {pub_date}", url=url)
        ])

    nav_buttons = []
    if start > 0:
        nav_buttons.append(InlineKeyboardButton(text="⬅️ Назад", callback_data=f"page_{page-1}"))
    if end < len(events):
        nav_buttons.append(InlineKeyboardButton(text="➡️ Вперёд", callback_data=f"page_{page+1}"))
    if nav_buttons:
        buttons.append(nav_buttons)

    buttons.append([InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_search")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

@router.callback_query(F.data == "search_reports")
async def start_search(callback: CallbackQuery, state: FSMContext):
    await callback.message.edit_text("🔍 Выберите компанию:", reply_markup=company_list_keyboard())
    await state.set_state(SearchStates.choosing_company)
    await callback.answer()

@router.callback_query(F.data.startswith("choose_company_"))
async def choose_company(callback: CallbackQuery, state: FSMContext):
    inn = callback.data.split("_")[2]
    await state.update_data(inn=inn)
    await callback.message.edit_text("📂 Загружаем типы отчётности...")

    try:
        # Получаем типы файлов (отчетности)
        types = await interfax_client.get_file_types()
    except Exception as e:
        await callback.message.edit_text(f"Ошибка получения типов: {e}")
        return

    await state.update_data(types=types)
    await state.set_state(SearchStates.choosing_type)
    await callback.message.edit_text("📂 Выберите тип отчётности:", reply_markup=type_list_keyboard(types))
    await callback.answer()

@router.callback_query(F.data.startswith("choose_type_"))
async def choose_type(callback: CallbackQuery, state: FSMContext):
    type_id = int(callback.data.split("_")[2])
    await state.update_data(file_type_id=type_id)
    await callback.message.edit_text("📅 Выберите год публикации:", reply_markup=year_list_keyboard())
    await state.set_state(SearchStates.choosing_year)
    await callback.answer()

@router.callback_query(F.data.startswith("choose_year_"))
async def choose_year(callback: CallbackQuery, state: FSMContext):
    year = int(callback.data.split("_")[2])  # Получаем выбранный год
    data = await state.get_data()  # Получаем данные из состояния
    inn = data["inn"]  # Получаем ИНН компании
    file_type_id = data["file_type_id"]  # Получаем тип отчета (категория)
    company_name = next((name for name, code in COMPANIES.items() if code == inn), "неизвестная компания")

    await callback.message.edit_text("⏳ Ищем отчёты...")

    try:
        # Получаем только отчеты с файлами, фильтруем по типу и году
        events = await interfax_client.get_filtered_reports(subject_code=inn, file_type=file_type_id, year=year)
    except Exception as e:
        await callback.message.edit_text(f"Ошибка при запросе: {e}")
        return

    if not events:
        await callback.message.edit_text(
            f"⛔️ Отчёты за {year} год не найдены для компании <b>{company_name}</b>.",
            reply_markup=main_menu(True)
        )
        return

    await state.update_data(events=events, page=0, company_name=company_name)
    await state.set_state(SearchStates.showing_results)

    text = (
        f"📥 <b>Найденные отчёты</b> для компании <b>{company_name}</b>:\n"
        f"Всего: {len(events)} документов."
    )

    await callback.message.edit_text(text, reply_markup=make_reports_keyboard(events, page=0))
    await callback.message.answer("📋 Главное меню:", reply_markup=main_menu(True))
    await callback.answer()

@router.callback_query(F.data == "cancel_search")
async def cancel_search(callback: CallbackQuery, state: FSMContext):
    await state.clear()

    # Проверка подписки пользователя для показа нужного главного меню
    from db import get_db
    is_sub = False
    with get_db() as conn:
        res = conn.execute(
            "SELECT is_subscribed FROM users WHERE user_id = ?", (callback.from_user.id,)
        ).fetchone()
        is_sub = bool(res["is_subscribed"]) if res else False

    # Перезаписываем текущее сообщение, чтобы не дублировать меню
    await callback.message.edit_text(
        "❌ Поиск отменён. Вы вернулись в главное меню.",
        reply_markup=main_menu(is_sub)
    )
    await callback.answer()
