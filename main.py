import asyncio
import logging
import os
from typing import Dict, List

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

# ========= Конфиг из переменных окружения =========
BOT_TOKEN = "8149079701:AAEFH-usiimRlsH0FYFqIeTVRhLCTwdSL9E"
ADMIN_CHAT_ID = -4956523911
BOT_USERNAME = "tsiryulnik_feedback_bot"

# ========= Логирование =========
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("tsiryulnik-bot")

# ========= Инициализация бота =========
bot = Bot(BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher()

# ========= Данные салонов =========
SALONS: Dict[str, Dict[str, str]] = {
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

# ========= Состояния =========
class Flow(StatesGroup):
    feedback_type = State()   # 'negative' | 'positive'
    salon = State()           # 's1' | 's2' | 's3'
    master_info = State()     # имя сотрудника или расположение рабочего места
    description = State()     # краткое описание (1–2 предложения) + (опц.) медиа
    phone = State()           # ввод/шаринг телефона или Пропустить

# ========= Кнопки / UI =========
def action_kb():
    kb = InlineKeyboardBuilder()
    kb.button(text="Оставить жалобу", callback_data="type:negative")
    kb.button(text="Оставить положительный отзыв", callback_data="type:positive")
    kb.adjust(1)
    return kb.as_markup()

def salons_kb():
    kb = InlineKeyboardBuilder()
    for key, s in SALONS.items():
        kb.button(text=s["name"], callback_data=f"salon:{key}")
    kb.adjust(1)
    return kb.as_markup()

def praise_links_kb(salon_key: str):
    s = SALONS[salon_key]
    kb = InlineKeyboardBuilder()
    kb.button(text="🟡 Яндекс", url=s["yandex"])
    kb.button(text="🟢 2ГИС", url=s["gis"])
    kb.button(text="🔵 VK", url=VK_LINK)
    kb.button(text="Готово, оставил(а)", callback_data="praise:done")
    kb.adjust(1)
    return kb.as_markup()

def contact_share_kb() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📞 Поделиться номером", request_contact=True)],
            [KeyboardButton(text="Пропустить")],
        ],
        resize_keyboard=True,
        one_time_keyboard=True,
        selective=True,
    )

# ========= Хелперы =========
async def admin_log(text: str):
    if ADMIN_CHAT_ID:
        try:
            await bot.send_message(ADMIN_CHAT_ID, text)
        except Exception as e:
            logger.exception("Не удалось отправить лог в группу: %s", e)

def get_username(u) -> str:
    return f"@{u.username}" if getattr(u, "username", None) else f"id:{u.id}"

# ========= Старт =========
@dp.message(CommandStart())
async def on_start(message: Message, state: FSMContext):
    """
    1) Сначала действие (Жалоба/Отзыв)
    2) Затем выбор салона (учитываем deep-link /start s1|s2|s3)
    """
    await state.clear()
    payload = message.text.split(maxsplit=1)
    if len(payload) == 2 and payload[1].strip() in SALONS:
        await state.update_data(salon=payload[1].strip())

    await message.answer("Что вы хотите сделать?", reply_markup=action_kb())
    await state.set_state(Flow.feedback_type)

@dp.callback_query(Flow.feedback_type, F.data.startswith("type:"))
async def on_pick_type(cb: CallbackQuery, state: FSMContext):
    typ = cb.data.split(":", 1)[1]  # 'negative' / 'positive'
    await state.update_data(feedback_type=typ)

    data = await state.get_data()
    preselected = data.get("salon")

    if preselected:
        if typ == "positive":
            await cb.message.edit_text(
                f"Салон: <b>{SALONS[preselected]['name']}</b>\n"
                f"Выберите площадку для отзыва:",
                reply_markup=praise_links_kb(preselected),
                disable_web_page_preview=True,
            )
            await admin_log(
                f"👍 Похвала\nСалон: {SALONS[preselected]['name']}\nПользователь: {get_username(cb.from_user)}"
            )
        else:
            await cb.message.edit_text(
                "Укажите имя сотрудника или напишите расположение его рабочего места."
            )
            await state.set_state(Flow.master_info)
    else:
        await cb.message.edit_text("Выберите салон:", reply_markup=salons_kb())
        await state.set_state(Flow.salon)

    await cb.answer()

@dp.callback_query(Flow.salon, F.data.startswith("salon:"))
async def on_pick_salon(cb: CallbackQuery, state: FSMContext):
    salon_key = cb.data.split(":", 1)[1]
    await state.update_data(salon=salon_key)
    data = await state.get_data()
    typ = data.get("feedback_type")

    if typ == "positive":
        await cb.message.edit_text(
            f"Салон: <b>{SALONS[salon_key]['name']}</b>\n"
            f"Выберите площадку для отзыва:",
            reply_markup=praise_links_kb(salon_key),
            disable_web_page_preview=True,
        )
        await admin_log(
            f"👍 Похвала\nСалон: {SALONS[salon_key]['name']}\nПользователь: {get_username(cb.from_user)}"
        )
    else:
        await cb.message.edit_text(
            "Укажите имя сотрудника или напишите расположение его рабочего места."
        )
        await state.set_state(Flow.master_info)

    await cb.answer()

# ========= Ветка: Положительный отзыв =========
@dp.callback_query(F.data == "praise:done")
async def on_praise_done(cb: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    salon_key = data.get("salon")
    salon_name = SALONS[salon_key]["name"] if salon_key else "—"
    await admin_log(
        "👍 Похвала (подтверждена)\n"
        f"Салон: {salon_name}\n"
        f"Пользователь: {get_username(cb.from_user)}"
    )
    await cb.message.edit_text("Спасибо! Это очень помогает салону 💈")
    await state.clear()
    await cb.answer()

# ========= Ветка: Жалоба =========
@dp.message(Flow.master_info)
async def on_master_info(message: Message, state: FSMContext):
    """
    Свободный ввод: имя сотрудника ИЛИ расположение рабочего места.
    Далее — сразу описание (1–2 предложения), без шага категорий и без слова «Готово».
    """
    info = (message.text or "").strip()
    await state.update_data(master_info=info)

    await message.answer(
        "Опишите, пожалуйста, ситуацию в 1–2 предложениях. "
        "Можно прикрепить фото/видео (не обязательно)."
    )
    await state.set_state(Flow.description)

@dp.message(Flow.description)
async def on_description(message: Message, state: FSMContext):
    """
    Принимаем первое осмысленное описание + (опционально) одно вложение,
    сразу переходим к запросу телефона (без «Готово»).
    """
    desc = (message.caption or message.text or "").strip()
    media = None
    if message.photo:
        media = f"photo:{message.photo[-1].file_id}"
    elif message.video:
        media = f"video:{message.video.file_id}"
    elif message.document:
        media = f"doc:{message.document.file_id}"

    await state.update_data(desc_text=desc, media=[media] if media else [])

    await message.answer(
        "Оставьте, пожалуйста, контактный номер телефона, чтобы мы могли связаться и решить вопрос.\n\n"
        "<i>Указывая телефон, вы даёте согласие на звонок от управляющего.</i>",
        reply_markup=contact_share_kb(),
    )
    await state.set_state(Flow.phone)

# ---- телефон: поделиться/пропустить/ввести
@dp.message(Flow.phone, F.contact)
async def on_phone_contact(message: Message, state: FSMContext):
    await finalize_complaint(message, state, phone=message.contact.phone_number)

@dp.message(Flow.phone, F.text.casefold() == "пропустить")
async def on_phone_skip(message: Message, state: FSMContext):
    await finalize_complaint(message, state, phone=None)

@dp.message(Flow.phone)
async def on_phone_text(message: Message, state: FSMContext):
    await finalize_complaint(message, state, phone=(message.text or "").strip())

async def finalize_complaint(message: Message, state: FSMContext, phone: str | None):
    data = await state.get_data()
    salon_key = data.get("salon")
    salon_name = SALONS[salon_key]["name"] if salon_key else "—"
    consent = bool(phone)  # телефон указан => согласие на звонок: Да

    log = (
        "🚨 Жалоба\n"
        f"Салон: {salon_name}\n"
        f"Сотрудник/место: {data.get('master_info') or '—'}\n"
        f"Описание: {data.get('desc_text') or '—'}\n"
        f"Медиа: {1 if data.get('media') else 0} влож.\n"
        f"Телефон: {phone or '—'}\n"
        f"Согласие на звонок: {'Да' if consent else 'Нет'}\n"
        f"Пользователь: {get_username(message.from_user)}"
    )
    await admin_log(log)

    await message.answer(
        "Спасибо! Ваша жалоба зафиксирована. "
        + ("Управляющий свяжется с вами в ближайшее время." if consent else "Мы разберёмся по факту обращения.")
    )
    await state.clear()

# ========= Help =========
@dp.message(Command("help"))
async def on_help(message: Message, state: FSMContext):
    deep = "\n".join(
        f"• {s['name']}: https://t.me/{BOT_USERNAME}?start={key}"
        for key, s in SALONS.items()
    )
    await message.answer(
        "Этот бот собирает жалобы и положительные отзывы.\n\n"
        "Как пользоваться:\n"
        "— /start → выберите действие (Жалоба/Отзыв)\n"
        "— выберите салон\n"
        "— следуйте подсказкам\n\n"
        "Быстрые ссылки по салонам:\n" + deep
    )

# ========= Мини-вебсервер для аптайма =========
async def handle(_):
    return web.Response(text="OK")

async def start_keepalive():
    app = web.Application()
    app.router.add_get("/", handle)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", 8080)
    await site.start()
    logger.info("Keepalive web server running on :8080")

# ========= main =========
async def main():
    if not BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN is not set")
    await admin_log("✅ Бот запущен. Жалобы/отзывы будут приходить сюда.")
    await asyncio.gather(
        dp.start_polling(bot),
        start_keepalive(),
    )

if __name__ == "__main__":
    asyncio.run(main())
