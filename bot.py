"""
Telegram-бот клиники (гидроколонотерапия, Алматы).

Простой рабочий бот на aiogram 3.x:
- приветствие и главное меню;
- услуги и цены;
- адрес и часы работы;
- частые вопросы (FAQ);
- запись на консультацию (имя + телефон + комментарий),
  заявка сразу пересылается администратору в Telegram.

Все тексты ниже — ЗАПОЛНИТЕ РЕАЛЬНЫМИ ДАННЫМИ КЛИНИКИ в блоке CONFIG.
Всё остальное трогать не обязательно.
"""

from __future__ import annotations

import asyncio
import logging
import os
from dataclasses import dataclass

from aiogram import Bot, Dispatcher, F, Router
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import (
    KeyboardButton,
    Message,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
)
from aiohttp import web

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("hydro_clinic_bot")

# ======================================================================
# CONFIG — замените плейсхолдеры на реальные данные клиники.
# ======================================================================

CLINIC_NAME = "Hydro Clinic Almaty"

ADDRESS_TEXT = (
    "📍 <b>Адрес и часы работы</b>\n\n"
    "Город: Алматы, [впишите улицу и дом]\n"
    "Часы работы: [например, ежедневно 10:00–20:00]\n"
    "Телефон: [впишите номер телефона]\n"
)

SERVICES_TEXT = (
    "💧 <b>Услуги и цены</b>\n\n"
    "• Гидроколонотерапия (1 сеанс) — [цена] ₸\n"
    "• Гидроколонотерапия (курс 3 сеанса) — [цена] ₸\n"
    "• Консультация специалиста — [цена] ₸\n\n"
    "Точные цены и список услуг уточняйте у администратора."
)

FAQ_TEXT = (
    "❓ <b>Частые вопросы</b>\n\n"
    "<b>Есть ли противопоказания?</b>\n"
    "Да, перед процедурой рекомендуется консультация специалиста. "
    "[уточните перечень противопоказаний]\n\n"
    "<b>Сколько длится сеанс?</b>\n"
    "[впишите длительность, например 45 минут]\n\n"
    "<b>Нужна ли подготовка перед процедурой?</b>\n"
    "[впишите рекомендации по подготовке]"
)

WELCOME_TEXT = (
    f"Здравствуйте! 👋 Это бот клиники <b>{CLINIC_NAME}</b>.\n\n"
    "Здесь можно узнать про услуги и цены, адрес и часы работы, "
    "частые вопросы, а также записаться на консультацию.\n\n"
    "Выберите пункт меню ниже 👇"
)

# ======================================================================
# Настройки из переменных окружения (секреты, не трогать)
# ======================================================================


@dataclass
class Settings:
    bot_token: str
    admin_chat_id: int
    port: int


def load_settings() -> Settings:
    token = os.environ.get("BOT_TOKEN", "").strip()
    admin_raw = os.environ.get("ADMIN_CHAT_ID", "").strip()
    port_raw = os.environ.get("PORT", "8080").strip()

    if not token:
        raise RuntimeError(
            "Не задана переменная окружения BOT_TOKEN "
            "(токен бота из @BotFather / из секрета CLINIC_BOT_TOKEN в Replit)."
        )
    if not admin_raw:
        raise RuntimeError(
            "Не задана переменная окружения ADMIN_CHAT_ID "
            "(chat_id администратора, которому приходят заявки на запись)."
        )
    try:
        admin_chat_id = int(admin_raw)
    except ValueError as exc:
        raise RuntimeError("ADMIN_CHAT_ID должен быть числом.") from exc

    return Settings(bot_token=token, admin_chat_id=admin_chat_id, port=int(port_raw))


# ======================================================================
# Клавиатуры
# ======================================================================

BTN_SERVICES = "💧 Услуги и цены"
BTN_ADDRESS = "📍 Адрес и часы работы"
BTN_FAQ = "❓ Частые вопросы"
BTN_BOOK = "📅 Записаться на консультацию"
BTN_CANCEL = "❌ Отменить"

main_menu = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text=BTN_SERVICES), KeyboardButton(text=BTN_ADDRESS)],
        [KeyboardButton(text=BTN_FAQ)],
        [KeyboardButton(text=BTN_BOOK)],
    ],
    resize_keyboard=True,
)

cancel_menu = ReplyKeyboardMarkup(
    keyboard=[[KeyboardButton(text=BTN_CANCEL)]],
    resize_keyboard=True,
)


# ======================================================================
# FSM запись на консультацию
# ======================================================================


class BookingForm(StatesGroup):
    name = State()
    phone = State()
    comment = State()


router = Router()


@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer(WELCOME_TEXT, reply_markup=main_menu)


@router.message(Command("menu"))
async def cmd_menu(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer("Главное меню:", reply_markup=main_menu)


@router.message(F.text == BTN_SERVICES)
async def show_services(message: Message) -> None:
    await message.answer(SERVICES_TEXT, reply_markup=main_menu)


@router.message(F.text == BTN_ADDRESS)
async def show_address(message: Message) -> None:
    await message.answer(ADDRESS_TEXT, reply_markup=main_menu)


@router.message(F.text == BTN_FAQ)
async def show_faq(message: Message) -> None:
    await message.answer(FAQ_TEXT, reply_markup=main_menu)


@router.message(F.text == BTN_CANCEL)
async def cancel_booking(message: Message, state: FSMContext) -> None:
    if await state.get_state() is None:
        return
    await state.clear()
    await message.answer("Запись отменена.", reply_markup=main_menu)


@router.message(F.text == BTN_BOOK)
async def start_booking(message: Message, state: FSMContext) -> None:
    await state.set_state(BookingForm.name)
    await message.answer(
        "Отлично! Как к вам обращаться? (введите имя)",
        reply_markup=cancel_menu,
    )


@router.message(BookingForm.name)
async def booking_name(message: Message, state: FSMContext) -> None:
    if not message.text:
        await message.answer("Пожалуйста, введите имя текстом.")
        return
    await state.update_data(name=message.text.strip())
    await state.set_state(BookingForm.phone)
    await message.answer("Укажите номер телефона для связи:")


@router.message(BookingForm.phone)
async def booking_phone(message: Message, state: FSMContext) -> None:
    if not message.text:
        await message.answer("Пожалуйста, введите номер телефона текстом.")
        return
    await state.update_data(phone=message.text.strip())
    await state.set_state(BookingForm.comment)
    await message.answer(
        "Укажите удобные дату/время или комментарий "
        "(или отправьте «-», если без комментария):"
    )


@router.message(BookingForm.comment)
async def booking_comment(message: Message, state: FSMContext, bot: Bot, admin_chat_id: int) -> None:
    comment = (message.text or "-").strip()
    data = await state.get_data()
    name = data.get("name", "—")
    phone = data.get("phone", "—")

    user = message.from_user
    username = f"@{user.username}" if user and user.username else "—"

    admin_text = (
        "📅 <b>Новая заявка на консультацию</b>\n\n"
        f"Имя: {name}\n"
        f"Телефон: {phone}\n"
        f"Комментарий: {comment}\n\n"
        f"Telegram: {username} (id {user.id if user else '—'})"
    )

    try:
        await bot.send_message(admin_chat_id, admin_text)
    except Exception:  # noqa: BLE001
        log.exception("Не удалось отправить заявку администратору")

    await state.clear()
    await message.answer(
        "Спасибо! Заявка отправлена, администратор свяжется с вами по указанному телефону.",
        reply_markup=main_menu,
    )


@router.message()
async def fallback(message: Message) -> None:
    await message.answer(
        "Не совсем понял 🙂 Пожалуйста, воспользуйтесь кнопками меню ниже, "
        "или отправьте /menu.",
        reply_markup=main_menu,
    )


# ======================================================================
# Мини HTTP-сервер (нужен для бесплатных Web Service на Render/Koyeb и т.п.,
# которым требуется, чтобы приложение слушало $PORT).
# ======================================================================


async def health(_request: web.Request) -> web.Response:
    return web.Response(text="ok")


async def run_web_server(port: int) -> None:
    app = web.Application()
    app.router.add_get("/", health)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, host="0.0.0.0", port=port)
    await site.start()
    log.info("Health-check server listening on port %s", port)


async def main() -> None:
    settings = load_settings()

    bot = Bot(
        token=settings.bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dp = Dispatcher(storage=MemoryStorage())
    dp.include_router(router)
    dp["admin_chat_id"] = settings.admin_chat_id

    await run_web_server(settings.port)

    log.info("Starting long polling…")
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
