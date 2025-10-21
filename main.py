import asyncio
import logging
import os
from typing import Dict

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

BOT_TOKEN = "8149079701:AAEFH-usiimRlsH0FYFqIeTVRhLCTwdSL9E"
ADMIN_CHAT_ID = -4956523911
BOT_USERNAME = "tsiryulnik_feedback_bot"

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("tsiryulnik-bot")

bot = Bot(BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher()

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


class Flow(StatesGroup):
    feedback_type = State()
    salon = State()
    master_info = State()
    description = State()
    phone = State()


def action_kb():
    kb = InlineKeyboardBuilder()
    kb.button(text="Оставить жалобу", callback_data="type:negative")
    kb.button(text="Оставить положительный отзыв", callback_data="type:positive")
    kb.adjust(1)
    return kb.as_markup()


def salons_kb():
    kb = InlineKeyboardBuilder()
    for key, s in SALONS.items():
