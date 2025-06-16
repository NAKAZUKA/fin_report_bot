from aiogram import Router, F, types
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from db import add_user_company, remove_user_company, list_user_companies
from clients.interfax_client import interfax_client
from db import get_db
from keyboards.main import main_menu

router = Router()

class CompanyStates(StatesGroup):
    waiting_for_inn = State()

def companies_keyboard(companies: list[dict]) -> InlineKeyboardMarkup:
    buttons = [
        [InlineKeyboardButton(text=f"❌ {c['company_name']} ({c['inn']})", callback_data=f"del_company_{c['inn']}")]
        for c in companies
    ]
    buttons.append([InlineKeyboardButton(text="➕ Добавить", callback_data="add_company")])
    buttons.append([InlineKeyboardButton(text="⬅️ Назад", callback_data="back_to_menu")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

@router.callback_query(F.data == "manage_companies")
async def manage_companies(callback: types.CallbackQuery):
    companies = list_user_companies(callback.from_user.id)
    if companies:
        await callback.message.edit_text("📄 <b>Ваши компании</b>:", reply_markup=companies_keyboard(companies))
    else:
        await callback.message.edit_text("📭 У вас нет сохранённых компаний. Добавьте первую:",
                                         reply_markup=companies_keyboard([]))
    await callback.answer()

@router.callback_query(F.data == "add_company")
async def ask_inn(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.edit_text("✍️ Введите ИНН или ОГРН компании:")
    await state.set_state(CompanyStates.waiting_for_inn)
    await callback.answer()

@router.message(CompanyStates.waiting_for_inn)
async def handle_inn_input(message: types.Message, state: FSMContext):
    code = message.text.strip()

    try:
        subject = await interfax_client.probe_company_info(code)
        if not subject:
            await message.answer("⚠️ Компания не найдена. Попробуйте ещё раз:\n\n✍️ Введите ИНН или ОГРН:")
            return  # Остаёмся в состоянии ожидания

        name = subject.get("shortName") or subject.get("fullName") or "Неизвестно"
        inn = subject.get("inn", code)
        ogrn = subject.get("ogrn", "")
        add_user_company(message.from_user.id, inn=inn, name=name, ogrn=ogrn)

        companies = list_user_companies(message.from_user.id)
        await message.answer(
            f"✅ Компания <b>{name}</b> добавлена.\n\n📄 <b>Ваш список компаний:</b>",
            reply_markup=companies_keyboard(companies)
        )
        await state.clear()
    except Exception as e:
        await message.answer(f"❌ Ошибка при запросе: {e}")
        await state.clear()

@router.callback_query(F.data.startswith("del_company_"))
async def delete_company(callback: types.CallbackQuery):
    inn = callback.data.split("_")[2]
    remove_user_company(callback.from_user.id, inn)
    companies = list_user_companies(callback.from_user.id)
    await callback.message.edit_text("📄 <b>Обновлён список компаний</b>:", reply_markup=companies_keyboard(companies))
    await callback.answer()

@router.callback_query(F.data == "back_to_menu")
async def back_to_main(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    with get_db() as conn:
        res = conn.execute("SELECT is_subscribed FROM users WHERE user_id = ?", (user_id,)).fetchone()
        is_sub = bool(res["is_subscribed"]) if res else False

    await callback.message.edit_text("📋 Главное меню:", reply_markup=main_menu(is_sub))
    await callback.answer()