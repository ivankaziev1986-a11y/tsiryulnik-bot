# -*- coding: utf-8 -*-
"""
Telegram feedback bot (aiogram v3) для сети ЦирюльникЪ
Версия: Replit-ready

Функционал:
✅ Один город, 3 салона
✅ Положительный отзыв → ссылки Яндекс / 2ГИС / VK
✅ Жалоба → мастер (знаю/не помню) → категории → описание + фото/видео → телефон (по желанию) → согласие на звонок
✅ Все обращения отправляются в группу Telegram (ADMIN_CHAT_ID)
"""

import asyncio
import logging
import os
from typing import Optional
from aiogram import Bot, Dispatcher, F
from aiogram.filters import CommandStart, Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message, ReplyKeyboardMarkup, KeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiohttp import web

logging.basicConfig(level=logging.INFO)

# ==== Настройки ====
BOT_TOKEN = "8149079701:AAEFH-usiimRlsH0FYFqIeTVRhLCTwdSL9E"
ADMIN_CHAT_ID = -4956523911
BOT_USERNAME = "tsiryulnik_feedback_bot"

VK_COMMON_URL = "https://vk.com/salonseverodvinsk"

SALONS = [
    {
        "id": "s1",
        "name": "Ломоносова, 85/1",
        "yandex": "https://yandex.ru/maps/-/CLbM5BiA",
        "two_gis": "https://go.2gis.com/U9V8N",
        "vk": VK_COMMON_URL,
    },
    {
        "id": "s2",
        "name": "Карла Маркса, 14",
        "yandex": "https://yandex.ru/maps/-/CLbMBIyc",
        "two_gis": "https://go.2gis.com/s3pVH",
        "vk": VK_COMMON_URL,
    },
    {
        "id": "s3",
        "name": "Мира, 8",
        "yandex": "https://yandex.ru/maps/-/CLbMB4YC",
        "two_gis": "https://go.2gis.com/PJtRI",
        "vk": VK_COMMON_URL,
    },
]

SALON_BY_ID = {s["id"]: s for s in SALONS}

CATEGORIES = [
    "Грубое общение",
    "Необработанный инструмент",
    "Грязное рабочее место",
    "Плохое качество услуги",
    "Нарушение времени записи",
    "Другое",
]


class Flow(StatesGroup):
    salon = State()
    action = State()
    know_master = State()
    master_name = State()
    categories = State()
    description = State()
    phone = State()
    consent = State()


# ==== Интерфейсные функции ====
def salons_kb():
    kb = InlineKeyboardBuilder()
    for s in SALONS:
        kb.button(text=s["name"], callback_data=f"salon:{s['id']}")
    kb.adjust(1)
    return kb.as_markup()


def action_kb():
    kb = InlineKeyboardBuilder()
    kb.button(text="Оставить жалобу", callback_data="act:complaint")
    kb.button(text="Оставить положительный отзыв", callback_data="act:praise")
    kb.adjust(1)
    return kb.as_markup()


def praise_kb(salon_id: str):
    s = SALON_BY_ID[salon_id]
    kb = InlineKeyboardBuilder()
    kb.button(text="Яндекс.Карты", url=s["yandex"])
    kb.button(text="2ГИС", url=s["two_gis"])
    kb.button(text="VK", url=s["vk"])
    kb.adjust(1)
    return kb.as_markup()


def know_master_kb():
    kb = InlineKeyboardBuilder()
    kb.button(text="Да, знаю (напишу)", callback_data="km:yes")
    kb.button(text="Не помню", callback_data="km:no")
    kb.adjust(1)
    return kb.as_markup()


def yes_no_kb(prefix: str = "cons"):
    kb = InlineKeyboardBuilder()
    kb.button(text="Да", callback_data=f"{prefix}:yes")
    kb.button(text="Нет", callback_data=f"{prefix}:no")
    kb.adjust(2)
    return kb.as_markup()


def contact_kb() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📞 Поделиться номером", request_contact=True)],
            [KeyboardButton(text="Пропустить")],
        ],
        resize_keyboard=True,
        one_time_keyboard=True,
        selective=True,
    )


def categories_hint() -> str:
    return (
        "Выберите категории проблемы (можно несколько).\n"
        "Отправьте одним сообщением, через запятую.\n\n"
        + "\n".join(f"• {c}" for c in CATEGORIES)
    )


async def send_admin_log(bot: Bot, text: str):
    try:
        await bot.send_message(ADMIN_CHAT_ID, text)
    except Exception as e:
        logging.exception(f"Не удалось отправить сообщение в группу: {e}")


# ==== Инициализация бота ====
bot = Bot(BOT_TOKEN, parse_mode="HTML")
dp = Dispatcher()


@dp.message(CommandStart())
async def start_cmd(message: Message, state: FSMContext):
    payload = message.text.split(maxsplit=1)
    preselected_salon: Optional[str] = None
    if len(payload) == 2:
        arg = payload[1].strip()
        if arg in SALON_BY_ID:
            preselected_salon = arg
    await state.clear()
    if preselected_salon:
        await state.update_data(salon_id=preselected_salon)
        s = SALON_BY_ID[preselected_salon]
        await message.answer(
            f"Вы выбрали салон: <b>{s['name']}</b>.\nЧто вы хотите сделать?",
            reply_markup=action_kb(),
        )
    else:
        await message.answer("Выберите салон:", reply_markup=salons_kb())
        await state.set_state(Flow.salon)


@dp.callback_query(F.data.startswith("salon:"))
async def pick_salon(cb: CallbackQuery, state: FSMContext):
    salon_id = cb.data.split(":", 1)[1]
    await state.update_data(salon_id=salon_id)
    s = SALON_BY_ID[salon_id]
    await cb.message.edit_text(
        f"Салон: <b>{s['name']}</b>\nВыберите действие:", reply_markup=action_kb()
    )
    await cb.answer()
    await state.set_state(Flow.action)


@dp.callback_query(F.data.startswith("act:"))
async def pick_action(cb: CallbackQuery, state: FSMContext):
    action = cb.data.split(":", 1)[1]
    data = await state.get_data()
    salon_id = data.get("salon_id")
    if action == "praise":
        await cb.message.edit_text(
            "Спасибо! Выберите площадку, где хотите оставить отзыв:",
            reply_markup=praise_kb(salon_id),
        )
        await send_admin_log(
            bot,
            f"👍 Похвала\nСалон: {SALON_BY_ID[salon_id]['name']}\nПользователь: @{cb.from_user.username or cb.from_user.id}",
        )
        await cb.answer()
    else:
        await cb.message.edit_text("Вы знаете имя мастера?", reply_markup=know_master_kb())
        await state.set_state(Flow.know_master)
        await cb.answer()


@dp.callback_query(F.data.startswith("km:"))
async def know_master(cb: CallbackQuery, state: FSMContext):
    yn = cb.data.split(":", 1)[1]
    if yn == "yes":
        await cb.message.edit_text("Напишите имя мастера (как на бейджике):")
        await state.set_state(Flow.master_name)
    else:
        await state.update_data(master_name=None)
        await cb.message.edit_text(categories_hint())
        await state.set_state(Flow.categories)
    await cb.answer()


@dp.message(Flow.master_name)
async def set_master_name(message: Message, state: FSMContext):
    name = (message.text or "").strip()
    await state.update_data(master_name=name)
    await message.answer(categories_hint())
    await state.set_state(Flow.categories)


@dp.message(Flow.categories)
async def set_categories(message: Message, state: FSMContext):
    chosen = [c.strip() for c in (message.text or "").split(",") if c.strip()]
    valid = [c if c in CATEGORIES else f"Другое: {c}" for c in chosen]
    await state.update_data(categories=valid)
    await message.answer(
        "Опишите ситуацию подробнее. Можно отправить фото или видео.\n\nКогда закончите — отправьте слово: <b>Готово</b>."
    )
    await state.set_state(Flow.description)


@dp.message(Flow.description, F.text.lower() == "готово")
async def finish_description_keyword(message: Message, state: FSMContext):
    await ask_phone(message, state)


@dp.message(Flow.description)
async def collect_description(message: Message, state: FSMContext):
    data = await state.get_data()
    desc = data.get("desc", "")
    media = data.get("media", [])
    if message.photo:
        media.append(f"photo:{message.photo[-1].file_id}")
    elif message.video:
        media.append(f"video:{message.video.file_id}")
    elif message.document:
        media.append(f"doc:{message.document.file_id}")
    part = message.caption or message.text or ""
    if part:
        desc = (desc + "\n" + part).strip()
    await state.update_data(desc=desc, media=media)


async def ask_phone(message: Message, state: FSMContext):
    await message.answer(
        "Чтобы мы могли связаться с вами и разобраться, оставьте номер телефона (по желанию)",
        reply_markup=contact_kb(),
    )
    await state.set_state(Flow.phone)


@dp.message(Flow.phone, F.contact)
async def got_contact(message: Message, state: FSMContext):
    phone = message.contact.phone_number
    await state.update_data(phone=phone)
    await ask_consent(message, state)


@dp.message(Flow.phone, F.text.casefold() == "пропустить")
async def skip_phone(message: Message, state: FSMContext):
    await state.update_data(phone=None)
    await ask_consent(message, state)


async def ask_consent(message: Message, state: FSMContext):
    await message.answer(
        "Согласны ли вы на звонок от управляющего для решения вопроса?",
        reply_markup=yes_no_kb("cons"),
    )
    await state.set_state(Flow.consent)


@dp.callback_query(Flow.consent, F.data.startswith("cons:"))
async def set_consent(cb: CallbackQuery, state: FSMContext):
    consent = cb.data.endswith("yes")
    await state.update_data(consent=consent)
    data = await state.get_data()
    salon = SALON_BY_ID[data["salon_id"]]
    user = cb.from_user
    log_lines = [
        "🚨 Жалоба",
        f"Салон: {salon['name']}",
        f"Мастер: {data.get('master_name') or '—'}",
        f"Категории: {', '.join(data.get('categories', [])) or '—'}",
        f"Описание: {data.get('desc', '—')}",
        f"Медиа: {len(data.get('media', []))} влож.",
        f"Телефон: {data.get('phone') or '—'}",
        f"Согласие на звонок: {'Да' if consent else 'Нет'}",
        f"Пользователь: @{user.username or user.id}",
    ]
    await send_admin_log(bot, "\n".join(log_lines))
    await cb.message.edit_text(
        "Спасибо! Ваша жалоба зафиксирована. Управляющий свяжется с вами в течение 24 часов."
        if consent
        else "Спасибо! Жалоба зафиксирована. Мы разберёмся."
    )
    await state.clear()
    await cb.answer()


async def start_keepalive_app():
    async def handle(_):
        return web.Response(text="OK")

    app = web.Application()
    app.router.add_get("/", handle)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", 8080)
    await site.start()


async def main():
    await send_admin_log(bot, "✅ Бот запущен. Жалобы будут приходить сюда.")
    await asyncio.gather(dp.start_polling(bot), start_keepalive_app())


if __name__ == "__main__":
    asyncio.run(main())
