"""
Telegram-бот клиники (гидроколонотерапия, Алматы).

Рабочий бот на aiogram 3.x:
- приветствие и главное меню с разделами (как в исходном проекте):
  о процедуре, как это работает, полезная информация, видео/фото материалы,
  частые вопросы, о специалисте, стоимость, подготовка, после процедуры,
  адрес и контакты;
- «Записаться на консультацию» — бот спрашивает имя, телефон и удобное время,
  затем сразу пересылает заявку администратору в Telegram.

Все тексты ниже — ЗАПОЛНИТЕ / ПРОВЕРЬТЕ РЕАЛЬНЫМИ ДАННЫМИ КЛИНИКИ в блоке CONFIG.
Общие описания процедуры (что это, как проходит, подготовка и т.д.) — типовые,
общепринятые формулировки, а не конкретный протокол вашей клиники. Перед
публикацией их обязательно должен проверить и при необходимости поправить
ваш специалист — особенно то, что касается противопоказаний.

Видео и фото материалы: положите файлы в папку `media/` рядом с bot.py и
перечислите их имена в MEDIA_FILES ниже — бот будет отправлять их пользователю.
Если список пуст, бот покажет текст-заглушку.
"""

from __future__ import annotations

import asyncio
import logging
import os
from dataclasses import dataclass
from pathlib import Path

from aiogram import Bot, Dispatcher, F, Router
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import (
    FSInputFile,
    KeyboardButton,
    Message,
    ReplyKeyboardMarkup,
)
from aiohttp import web

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("hydro_clinic_bot")

BASE_DIR = Path(__file__).resolve().parent

# ======================================================================
# CONFIG — замените плейсхолдеры на реальные данные клиники.
# ======================================================================

CLINIC_NAME = "Hydro Clinic Almaty"

WELCOME_TEXT = (
    f"👋 Добро пожаловать в <b>{CLINIC_NAME}</b>!\n\n"
    "Здесь можно узнать больше о гидроколонотерапии, познакомиться со "
    "специалистом, посмотреть полезные материалы и записаться на консультацию.\n\n"
    "Выберите интересующий раздел 👇"
)

PROCEDURE_WHAT_TEXT = (
    "🩺 <b>О процедуре</b>\n\n"
    "Гидроколонотерапия — это процедура очищения толстого кишечника с помощью "
    "воды под контролем специалиста и с использованием специального "
    "оборудования. Она помогает мягко вывести застойное содержимое кишечника "
    "и подготовить организм к дальнейшим программам оздоровления.\n\n"
    "Как и у любой медицинской процедуры, у гидроколонотерапии есть "
    "противопоказания — точный список для вас определит специалист на "
    "консультации."
)

HOW_IT_WORKS_TEXT = (
    "🔬 <b>Как проходит процедура</b>\n\n"
    "Вы располагаетесь на кушетке, специалист вводит одноразовый стерильный "
    "наконечник. Через закрытую систему в кишечник постепенно поступает "
    "очищенная тёплая вода, специалист мягко массирует живот, способствуя "
    "выведению содержимого. Всё происходит в закрытой системе, вы можете в "
    "любой момент обсудить самочувствие со специалистом.\n\n"
    "Средняя продолжительность сеанса — 30–45 минут."
)

USEFUL_INFO_TEXT = (
    "📚 <b>Полезная информация</b>\n\n"
    "Гидроколонотерапию часто рекомендуют как часть программ детокса и "
    "оздоровления кишечника, при подготовке к диагностическим процедурам, а "
    "также при отдельных нарушениях работы ЖКТ. Количество и периодичность "
    "сеансов подбирает специалист индивидуально после консультации.\n\n"
    "Чтобы узнать, подходит ли процедура именно вам, запишитесь на "
    "консультацию — кнопка «📅 Записаться на консультацию»."
)

# Список файлов в папке media/, которые бот будет присылать по кнопке
# «Видео и фото материалы» (jpg/jpeg/png — как фото, mp4/mov — как видео).
# Пример: MEDIA_FILES = ["clinic1.jpg", "procedure_demo.mp4"]
MEDIA_FILES: list[str] = []

MEDIA_FALLBACK_TEXT = (
    "🎥 <b>Видео и фото материалы</b>\n\n"
    "Мы скоро добавим сюда фото и видео нашей клиники и процедуры. "
    "А пока вы можете задать любой вопрос — «📅 Записаться на консультацию»."
)

FAQ_TEXT = (
    "❓ <b>Частые вопросы</b>\n\n"
    "<b>Больно ли это?</b>\n"
    "Нет, процедура не должна вызывать боль. О любом дискомфорте стоит сразу "
    "сообщить специалисту.\n\n"
    "<b>Сколько длится сеанс?</b>\n"
    "Обычно 30–45 минут.\n\n"
    "<b>Как часто можно делать процедуру?</b>\n"
    "Частоту и количество сеансов определяет специалист индивидуально.\n\n"
    "<b>Нужна ли подготовка?</b>\n"
    "Да, рекомендации — в разделе «📋 Подготовка».\n\n"
    "<b>Есть ли противопоказания?</b>\n"
    "Да, полный список уточняется на консультации со специалистом."
)

SPECIALIST_TEXT = (
    "👨‍⚕️ <b>О специалисте</b>\n\n"
    "[Впишите имя и квалификацию специалиста, опыт работы, при желании — "
    "фото. Эту информацию нужно предоставить вам — здесь пока заглушка.]"
)

PRICE_TEXT = (
    "💰 <b>Стоимость</b>\n\n"
    "• Гидроколонотерапия (1 сеанс) — [цена] ₸\n"
    "• Курс из 3 сеансов — [цена] ₸\n"
    "• Консультация специалиста — [цена] ₸\n\n"
    "Точные цены уточняйте у администратора — «📅 Записаться на консультацию»."
)

PREPARATION_TEXT = (
    "📋 <b>Подготовка к процедуре</b>\n\n"
    "За 1–2 дня до сеанса рекомендуется лёгкое питание: исключить жирную, "
    "жареную и тяжёлую пищу, алкоголь и газированные напитки. В день "
    "процедуры желателен лёгкий завтрак или отказ от еды за 2 часа до сеанса.\n\n"
    "Индивидуальные рекомендации даст специалист на консультации."
)

AFTER_TEXT = (
    "🌿 <b>После процедуры</b>\n\n"
    "В течение дня рекомендуется лёгкое питание и достаточное количество "
    "воды, при необходимости — приём пробиотиков по рекомендации "
    "специалиста.\n\n"
    "Если почувствуете себя плохо — обратитесь к специалисту клиники."
)

ADDRESS_TEXT = (
    "📍 <b>Адрес и часы работы</b>\n\n"
    "Город: Алматы, [впишите улицу и дом]\n"
    "Часы работы: [например, ежедневно 10:00–20:00]\n"
    "Телефон: [впишите номер телефона]\n"
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

BTN_PROCEDURE = "🩺 О процедуре"
BTN_HOW_IT_WORKS = "🔬 Как это работает"
BTN_USEFUL_INFO = "📚 Полезная информация"
BTN_MEDIA = "🎥 Видео и фото материалы"
BTN_FAQ = "❓ Частые вопросы"
BTN_SPECIALIST = "👨‍⚕️ О специалисте"
BTN_PRICE = "💰 Стоимость"
BTN_PREPARATION = "📋 Подготовка"
BTN_AFTER = "🌿 После процедуры"
BTN_ADDRESS = "📍 Адрес и контакты"
BTN_BOOK = "📅 Записаться на консультацию"
BTN_CANCEL = "❌ Отменить"

main_menu = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text=BTN_PROCEDURE), KeyboardButton(text=BTN_HOW_IT_WORKS)],
        [KeyboardButton(text=BTN_USEFUL_INFO), KeyboardButton(text=BTN_MEDIA)],
        [KeyboardButton(text=BTN_FAQ), KeyboardButton(text=BTN_SPECIALIST)],
        [KeyboardButton(text=BTN_PRICE), KeyboardButton(text=BTN_PREPARATION)],
        [KeyboardButton(text=BTN_AFTER), KeyboardButton(text=BTN_ADDRESS)],
        [KeyboardButton(text=BTN_BOOK)],
    ],
    resize_keyboard=True,
)

cancel_menu = ReplyKeyboardMarkup(
    keyboard=[[KeyboardButton(text=BTN_CANCEL)]],
    resize_keyboard=True,
)

# Простые текстовые разделы: кнопка -> текст ответа.
SIMPLE_SECTIONS: dict[str, str] = {
    BTN_PROCEDURE: PROCEDURE_WHAT_TEXT,
    BTN_HOW_IT_WORKS: HOW_IT_WORKS_TEXT,
    BTN_USEFUL_INFO: USEFUL_INFO_TEXT,
    BTN_FAQ: FAQ_TEXT,
    BTN_SPECIALIST: SPECIALIST_TEXT,
    BTN_PRICE: PRICE_TEXT,
    BTN_PREPARATION: PREPARATION_TEXT,
    BTN_AFTER: AFTER_TEXT,
    BTN_ADDRESS: ADDRESS_TEXT,
}


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


@router.message(F.text.in_(SIMPLE_SECTIONS.keys()))
async def show_section(message: Message) -> None:
    text = SIMPLE_SECTIONS[message.text]
    await message.answer(text, reply_markup=main_menu)


@router.message(F.text == BTN_MEDIA)
async def show_media(message: Message) -> None:
    if not MEDIA_FILES:
        await message.answer(MEDIA_FALLBACK_TEXT, reply_markup=main_menu)
        return

    sent_any = False
    for filename in MEDIA_FILES:
        file_path = BASE_DIR / "media" / filename
        if not file_path.is_file():
            log.warning("Файл материала не найден: %s", file_path)
            continue
        suffix = file_path.suffix.lower()
        try:
            if suffix in {".mp4", ".mov", ".m4v"}:
                await message.answer_video(FSInputFile(file_path))
            else:
                await message.answer_photo(FSInputFile(file_path))
            sent_any = True
        except Exception:  # noqa: BLE001
            log.exception("Не удалось отправить файл материала: %s", file_path)

    if not sent_any:
        await message.answer(MEDIA_FALLBACK_TEXT)
    await message.answer("Вернуться в меню можно кнопками ниже 👇", reply_markup=main_menu)


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
