import asyncio
import logging
import os
from typing import Optional, Set, Dict, Any, List

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

# ========= Категории жалобы =========
CATEGORIES: List[str] = [
    "Грубое общение",
    "Необработанный инструмент",
    "Грязное рабочее место",
    "Плохое качество услуги",
    "Нарушение времени записи",
    "Другое",
]

# ========= Состояния =========
class Flow(StatesGroup):
    feedback_type = State()   # 'negative' | 'positive'
    salon = State()           # 's1' | 's2' | 's3'
    master_info = State()     # свободный ввод: имя сотрудника или расположение рабочего места
    cats = State()            # выбор категорий (инлайн чекбоксы)
    desc = State()            # описание + медиа, завершается словом "Готово"
    phone = State()           # получить контакт или "Пропустить"
    consent = State()         # согласие на звонок (Да/Нет)

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

def categories_kb(selected: Set[str]):
    kb = InlineKeyboardBuilder()
    for idx, c in enumerate(CATEGORIES):
        mark = "✅ " if c in selected else ""
        kb.button(text=f"{mark}{c}", callback_data=f"cat:{idx}")
    kb.button(text="Готово", callback_data="cat:done")
    kb.adjust(1)
    return kb.as_markup()

# ========= Помощники =========
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
    Сначала спрашиваем действие. Если есть deep-link /start s2 — запоминаем салон,
    но всё равно сперва показываем выбор действия (требование п.1).
    """
    await state.clear()
    # deep-link: /start s1|s2|s3
    payload = message.text.split(maxsplit=1)
    if len(payload) == 2:
        arg = payload[1].strip()
        if arg in SALONS:
            await state.update_data(salon=arg)

    await message.answer("Что вы хотите сделать?", reply_markup=action_kb())
    await state.set_state(Flow.feedback_type)

@dp.callback_query(Flow.feedback_type, F.data.startswith("type:"))
async def on_pick_type(cb: CallbackQuery, state: FSMContext):
    typ = cb.data.split(":", 1)[1]  # 'negative' / 'positive'
    await state.update_data(feedback_type=typ)

    data = await state.get_data()
    preselected = data.get("salon")

    if preselected:
        # Салон уже известен из deep-link
        if typ == "positive":
            await cb.message.edit_text(
                f"Салон: <b>{SALONS[preselected]['name']}</b>\n"
                f"Выберите площадку для отзыва:",
                reply_markup=praise_links_kb(preselected),
                disable_web_page_preview=True,
            )
            await admin_log(f"👍 Похвала\nСалон: {SALONS[preselected]['name']}\nПользователь: {get_username(cb.from_user)}")
        else:
            await cb.message.edit_text(
                "Укажите имя сотрудника или напишите расположение его рабочего места."
            )
            await state.set_state(Flow.master_info)
    else:
        # Нужно выбрать салон
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
        await admin_log(f"👍 Похвала\nСалон: {SALONS[salon_key]['name']}\nПользователь: {get_username(cb.from_user)}")
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
    Далее — мультивыбор категорий (инлайн чекбоксы).
    """
    info = (message.text or "").strip()
    await state.update_data(master_info=info)

    await message.answer(
        "Выберите категории проблемы (можно несколько), затем нажмите «Готово».",
        reply_markup=categories_kb(set())
    )
    await state.set_state(Flow.cats)

@dp.callback_query(Flow.cats, F.data.startswith("cat:"))
async def on_toggle_category(cb: CallbackQuery, state: FSMContext):
    code = cb.data.split(":", 1)[1]
    data = await state.get_data()
    selected: Set[str] = set(data.get("cats", []))

    if code == "done":
        # Переходим к описанию/медиа
        await cb.message.edit_text(
            "Опишите ситуацию (1–2 предложения). Можно прикрепить фото/видео.\n\n"
            "Когда закончите, отправьте сообщение словом: <b>Готово</b>."
        )
        await state.set_state(Flow.desc)
        await cb.answer()
        return

    # Переключаем пункт
    try:
        idx = int(code)
        if 0 <= idx < len(CATEGORIES):
            cat = CATEGORIES[idx]
            if cat in selected:
                selected.remove(cat)
            else:
                selected.add(cat)
    except ValueError:
        pass

    await state.update_data(cats=list(selected))
    await cb.message.edit_reply_markup(categories_kb(selected))
    await cb.answer()

# ---- сбор описания/медиа до слова "Готово"
@dp.message(Flow.desc, F.text.lower() == "готово")
async def on_desc_done(message: Message, state: FSMContext):
    await message.answer(
        "Оставьте номер телефона (по желанию).",
        reply_markup=contact_share_kb()
    )
    await state.set_state(Flow.phone)

@dp.message(Flow.desc)
async def on_desc_collect(message: Message, state: FSMContext):
    data = await state.get_data()
    desc = data.get("desc_text", "")
    media = data.get("media", [])

    # Медиа
    if message.photo:
        media.append(f"photo:{message.photo[-1].file_id}")
    elif message.video:
        media.append(f"video:{message.video.file_id}")
    elif message.document:
        media.append(f"doc:{message.document.file_id}")

    # Текст / подпись
    part = message.caption or message.text or ""
    if part and part.lower() != "готово":
        desc = (desc + "\n" + part).strip()

    await state.update_data(desc_text=desc, media=media)

# ---- телефон: поделиться/пропустить/ввести
@dp.message(Flow.phone, F.contact)
async def on_phone_contact(message: Message, state: FSMContext):
    await state.update_data(phone=message.contact.phone_number)
    await ask_consent(message, state)

@dp.message(Flow.phone, F.text.casefold() == "пропустить")
async def on_phone_skip(message: Message, state: FSMContext):
    await state.update_data(phone=None)
    await ask_consent(message, state)

@dp.message(Flow.phone)
async def on_phone_text(message: Message, state: FSMContext):
    await state.update_data(phone=(message.text or "").strip())
    await ask_consent(message, state)

async def ask_consent(message: Message, state: FSMContext):
    kb = InlineKeyboardBuilder()
    kb.button(text="Да", callback_data="cons:yes")
    kb.button(text="Нет", callback_data="cons:no")
    kb.adjust(2)
    await message.answer(
        "Согласны ли вы на звонок от управляющего для решения вопроса?",
        reply_markup=kb.as_markup(),
    )
    await state.set_state(Flow.consent)

@dp.callback_query(Flow.consent, F.data.startswith("cons:"))
async def on_consent(cb: CallbackQuery, state: FSMContext):
    consent = cb.data.endswith("yes")
    data = await state.get_data()

    salon_key = data.get("salon")
    salon_name = SALONS[salon_key]["name"] if salon_key else "—"
    cats = ", ".join(data.get("cats", [])) or "—"

    log = (
        "🚨 Жалоба\n"
        f"Салон: {salon_name}\n"
        f"Сотрудник/место: {data.get('master_info') or '—'}\n"
        f"Категории: {cats}\n"
        f"Описание: {data.get('desc_text') or '—'}\n"
        f"Медиа: {len(data.get('media', []))} влож.\n"
        f"Телефон: {data.get('phone') or '—'}\n"
        f"Согласие на звонок: {'Да' if consent else 'Нет'}\n"
        f"Пользователь: {get_username(cb.from_user)}"
    )
    await admin_log(log)

    await cb.message.edit_text(
        "Спасибо! Ваша жалоба зафиксирована. Управляющий свяжется с вами в течение 24 часов."
        if consent else
        "Спасибо! Жалоба зафиксирована. Мы разберёмся."
    )
    await state.clear()
    await cb.answer()

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
