# ✅ handlers/search.py

from aiogram import Router, F, types
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.types.input_file import FSInputFile
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from datetime import datetime

from db import list_user_companies, get_db
from clients.interfax_client import interfax_client
from keyboards.main import main_menu

router = Router()


class SearchStates(StatesGroup):
    choosing_company = State()
    choosing_category = State()
    choosing_year = State()
    showing_results = State()


CATEGORIES = [
    "бухгалтерская", "финансовая", "МСФО", "консолидированная", "годовая"
]

CATEGORY_KEYBOARD = InlineKeyboardMarkup(
    inline_keyboard=[
        [InlineKeyboardButton(text=c.title(), callback_data=f"cat_{c}")] for c in CATEGORIES
    ] + [[InlineKeyboardButton(text="⬅️ Назад", callback_data="back_to_menu")]]
)


def years_keyboard() -> InlineKeyboardMarkup:
    current_year = datetime.now().year
    buttons = [
        [InlineKeyboardButton(text=str(y), callback_data=f"year_{y}")]
        for y in range(current_year, current_year - 5, -1)
    ]
    buttons.append([InlineKeyboardButton(text="⬅️ Назад", callback_data="back_to_menu")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


@router.callback_query(F.data == "search_reports")
async def search_start(callback: types.CallbackQuery, state: FSMContext):
    companies = list_user_companies(callback.from_user.id)
    if not companies:
        await callback.message.edit_text("❌ У вас нет сохранённых компаний.")
        return

    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=f"{c['company_name']} ({c['inn']})", callback_data=f"company_{c['inn']}")]
            for c in companies
        ] + [[InlineKeyboardButton(text="⬅️ Назад", callback_data="back_to_menu")]]
    )
    await callback.message.edit_text("🔍 Выберите компанию для поиска:", reply_markup=kb)
    await state.set_state(SearchStates.choosing_company)
    await callback.answer()


@router.callback_query(SearchStates.choosing_company, F.data.startswith("company_"))
async def choose_category(callback: types.CallbackQuery, state: FSMContext):
    inn = callback.data.split("_")[1]
    await state.update_data(subject_code=inn)
    await callback.message.edit_text("🗂 Выберите категорию отчётности:", reply_markup=CATEGORY_KEYBOARD)
    await state.set_state(SearchStates.choosing_category)
    await callback.answer()


@router.callback_query(SearchStates.choosing_category, F.data.startswith("cat_"))
async def choose_year(callback: types.CallbackQuery, state: FSMContext):
    category = callback.data.split("_", 1)[1]
    await state.update_data(category=category)
    await callback.message.edit_text("📅 Выберите год публикации:", reply_markup=years_keyboard())
    await state.set_state(SearchStates.choosing_year)
    await callback.answer()


@router.callback_query(SearchStates.choosing_year, F.data.startswith("year_"))
async def show_results(callback: types.CallbackQuery, state: FSMContext):
    year = int(callback.data.split("_")[1])
    data = await state.get_data()
    subject_code = data["subject_code"]
    category = data["category"]

    await callback.message.edit_text("🔄 Поиск отчётов...")

    try:
        results = await interfax_client.search_reports_by_category(subject_code, category, year)
    except Exception as e:
        await callback.message.edit_text(f"❌ Ошибка при поиске: {e}")
        await state.clear()
        return

    if not results:
        await callback.message.edit_text("📭 Ничего не найдено по вашему запросу.")
        with get_db() as conn:
            res = conn.execute("SELECT is_subscribed FROM users WHERE user_id = ?", (callback.from_user.id,)).fetchone()
            is_sub = bool(res["is_subscribed"]) if res else False
        await callback.message.answer("🏠 Возврат в главное меню.", reply_markup=main_menu(is_sub))
        await state.clear()
        return

    await state.update_data(results=results, offset=0)
    await show_next_batch(callback.message, state)


async def show_next_batch(message: types.Message, state: FSMContext):
    data = await state.get_data()
    results = data.get("results", [])
    offset = data.get("offset", 0)
    batch = results[offset:offset + 10]

    for r in batch:
        file = r["file"]
        attrs = file["attributes"]

        caption = (
            f"🏢 <b>{r['subject'].get('shortName', 'Компания')}</b>\n"
            f"📄 <b>{file['type']['name']}</b>\n"
            f"🗓 Год: <b>{attrs.get('YearRep', 'не указано')}</b>\n"
            f"🗓 Дата публикации: <b>{attrs.get('DatePub', '-')}</b>"
        )

        try:
            pdf_paths = await interfax_client.download_and_extract_file(file)
            if pdf_paths:
                # создаём имя файла из атрибутов
                name_part = file['type']['name'].replace(" ", "_")
                uid = file.get("uid", "")[:6]
                year = attrs.get("YearRep", "год")
                clean_filename = f"{name_part}_{year}_{uid}.pdf"

                doc = FSInputFile(path=pdf_paths[0], filename=clean_filename)
                await message.answer_document(document=doc, caption=caption, parse_mode="HTML")
            else:
                await message.answer(f"{caption}\n❌ Не удалось получить файл.")
        except Exception as e:
            await message.answer(f"{caption}\n❌ Ошибка при скачивании: {e}")

    new_offset = offset + len(batch)
    if new_offset < len(results):
        await state.update_data(offset=new_offset)
        await message.answer("⬇️ Показать ещё отчёты", reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[[InlineKeyboardButton(text="🔽 Показать ещё", callback_data="show_more")]]
        ))
        await state.set_state(SearchStates.showing_results)
    else:
        with get_db() as conn:
            res = conn.execute("SELECT is_subscribed FROM users WHERE user_id = ?", (message.chat.id,)).fetchone()
            is_sub = bool(res["is_subscribed"]) if res else False
        await message.answer("✅ Все результаты показаны.", reply_markup=main_menu(is_sub))
        await state.clear()


@router.callback_query(SearchStates.showing_results, F.data == "show_more")
async def show_more(callback: types.CallbackQuery, state: FSMContext):
    await show_next_batch(callback.message, state)
    await callback.answer()
