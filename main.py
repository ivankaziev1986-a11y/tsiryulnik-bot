import asyncio
import logging
import os
from typing import Optional

from aiogram import Bot, Dispatcher, F
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import CommandStart, Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    CallbackQuery,
    Message,
    ReplyKeyboardMarkup,
    KeyboardButton,
)
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiohttp import web

# === Настройки ===
BOT_TOKEN = "8149079701:AAEFH-usiimRlsH0FYFqIeTVRhLCTwdSL9E"
ADMIN_CHAT_ID = -4956523911
BOT_USERNAME = "tsiryulnik_feedback_bot"

# === Логирование ===
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# === Инициализация бота и диспетчера ===
bot = Bot(BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher()

# === Список салонов ===
salons = {
    "s1": {
        "name": "Ломоносова, 85/1",
        "yandex": "https://yandex.ru/maps/-/CLbM5BiA",
        "gis": "https://go.2gis.com/U9V8N",
    },
    "s2": {
        "name": "Карла Маркса, 14",
        "yandex": "https://yandex.ru/maps/-/CLbMBIyc",
        "gis": "https://go.2gis.com/s3pVH",
    },
    "s3": {
        "name": "Мира, 8",
        "yandex": "https://yandex.ru/maps/-/CLbMB4YC",
        "gis": "https://go.2gis.com/PJtRI",
    },
}

VK_LINK = "https://vk.com/salonseverodvinsk"

# === Машина состояний ===
class FeedbackForm(StatesGroup):
    salon = State()
    feedback_type = State()
    master_name = State()
    issue_text = State()
    phone = State()
    consent = State()


# === Команда /start ===
@dp.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
    builder = InlineKeyboardBuilder()
    for key, s in salons.items():
        builder.button(text=s["name"], callback_data=f"salon_{key}")
    await message.answer(
        "Выберите салон, где вы были:",
        reply_markup=builder.as_markup(),
    )
    await state.set_state(FeedbackForm.salon)


# === Выбор салона ===
@dp.callback_query(F.data.startswith("salon_"))
async def choose_salon(callback: CallbackQuery, state: FSMContext):
    salon_key = callback.data.split("_")[1]
    await state.update_data(salon=salon_key)

    builder = InlineKeyboardBuilder()
    builder.button(text="Оставить жалобу", callback_data="type_negative")
    builder.button(text="Оставить положительный отзыв", callback_data="type_positive")

    await callback.message.edit_text(
        "Хотите оставить жалобу или положительный отзыв?",
        reply_markup=builder.as_markup(),
    )
    await state.set_state(FeedbackForm.feedback_type)


# === Ветка: положительный отзыв ===
@dp.callback_query(F.data == "type_positive")
async def positive_feedback(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    salon = salons[data["salon"]]
    text = (
        f"Спасибо за ваш отзыв!\n\n"
        f"Пожалуйста, выберите площадку, где хотите его оставить:\n\n"
        f"📍 {salon['name']}\n\n"
        f"<a href='{salon['yandex']}'>🟡 Яндекс</a>\n"
        f"<a href='{salon['gis']}'>🟢 2ГИС</a>\n"
        f"<a href='{VK_LINK}'>🔵 ВКонтакте</a>"
    )
    await callback.message.edit_text(text, disable_web_page_preview=True)
    await state.clear()


# === Ветка: жалоба ===
@dp.callback_query(F.data == "type_negative")
async def negative_feedback(callback: CallbackQuery, state: FSMContext):
    kb = ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="Да"), KeyboardButton(text="Не помню")]],
        resize_keyboard=True,
        one_time_keyboard=True,
    )
    await callback.message.answer(
        "Вы знаете имя мастера? (указано на бейджике)", reply_markup=kb
    )
    await state.set_state(FeedbackForm.master_name)


@dp.message(FeedbackForm.master_name)
async def process_master_name(message: Message, state: FSMContext):
    name = message.text if message.text != "Не помню" else None
    await state.update_data(master_name=name)

    await message.answer(
        "Пожалуйста, опишите проблему. Например:\n"
        "— Грубое обращение\n— Плохое качество услуги\n— Грязное рабочее место\n— Необработанный инструмент",
        reply_markup=ReplyKeyboardMarkup(
            keyboard=[[KeyboardButton(text="Отменить")]], resize_keyboard=True
        ),
    )
    await state.set_state(FeedbackForm.issue_text)


@dp.message(FeedbackForm.issue_text)
async def process_issue_text(message: Message, state: FSMContext):
    if message.text.lower() == "отменить":
        await message.answer("Отмена. Вы можете начать заново /start")
        await state.clear()
        return

    await state.update_data(issue_text=message.text)
    await message.answer("Оставьте, пожалуйста, свой номер телефона (или напишите «нет»).")
    await state.set_state(FeedbackForm.phone)


@dp.message(FeedbackForm.phone)
async def process_phone(message: Message, state: FSMContext):
    await state.update_data(phone=message.text)
    kb = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="Да, перезвоните мне")],
            [KeyboardButton(text="Нет, только учтите мой отзыв")],
        ],
        resize_keyboard=True,
    )
    await message.answer("Можно ли вам перезвонить для уточнения деталей?", reply_markup=kb)
    await state.set_state(FeedbackForm.consent)


@dp.message(FeedbackForm.consent)
async def process_consent(message: Message, state: FSMContext):
    data = await state.get_data()
    salon = salons[data["salon"]]

    complaint = (
        f"⚠️ <b>Новая жалоба</b>\n\n"
        f"🏠 Салон: {salon['name']}\n"
        f"👤 Мастер: {data.get('master_name', 'Не указано')}\n"
        f"📄 Описание: {data.get('issue_text')}\n"
        f"📞 Телефон: {data.get('phone')}\n"
        f"☑️ Согласие на звонок: {message.text}\n"
    )

    await bot.send_message(ADMIN_CHAT_ID, complaint)
    await message.answer(
        "Спасибо, что сообщили о проблеме. Мы обязательно разберёмся в ситуации 🙏",
        reply_markup=ReplyKeyboardMarkup(
            keyboard=[[KeyboardButton(text="/start")]], resize_keyboard=True
        ),
    )
    await state.clear()


# === Мини веб-сервер для аптайма ===
async def handle(request):
    return web.Response(text="Bot is running")

def setup_web_server():
    app = web.Application()
    app.router.add_get("/", handle)
    return app


# === Главная точка входа ===
async def main():
    app = setup_web_server()
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", 8080)
    await site.start()

    logger.info("✅ Бот запущен. Жалобы будут приходить сюда.")
    await bot.send_message(ADMIN_CHAT_ID, "✅ Бот запущен. Жалобы будут приходить сюда.")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
