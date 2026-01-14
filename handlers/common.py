from aiogram import types, Bot
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove
from aiogram.utils.keyboard import InlineKeyboardBuilder, ReplyKeyboardBuilder
from aiogram.fsm.state import State, StatesGroup
from constants.messages import Messages
import os
import logging

logger = logging.getLogger(__name__)

class QuizStates(StatesGroup):
    WAITING_FOR_DOCX = State()
    WAITING_FOR_TITLE = State()
    WAITING_FOR_SHUFFLE = State()
    QUIZ_READY = State()
    WAITING_FOR_AI_TOPIC = State()  # New state for AI quiz generation
    WAITING_FOR_AI_COUNT = State()  # New state for AI question count
    WAITING_FOR_CONVERT_FILE = State()  # New state for AI test conversion
    ADMIN_AI_SETTINGS = State()
    ADMIN_SETTING_GENERATE_COOLDOWN = State()
    ADMIN_SETTING_CONVERT_COOLDOWN = State()

def get_main_keyboard(lang: str, user_id: int = None):
    builder = ReplyKeyboardBuilder()
    builder.button(text=Messages.get("AI_GENERATE_BTN", lang))
    builder.button(text=Messages.get("CONVERT_BTN", lang))
    builder.button(text=Messages.get("UPLOAD_WORD_BTN", lang))
    builder.button(text=Messages.get("MY_QUIZZES_BTN", lang))
    builder.button(text=Messages.get("ADD_TO_GROUP_BTN", lang))
    builder.button(text=Messages.get("SET_LANGUAGE_BTN", lang))
    builder.button(text=Messages.get("HELP_BTN", lang))
    
    # Admin buttons
    from core.config import settings
    if user_id == settings.ADMIN_ID:
        builder.button(text=Messages.get("ADMIN_USERS_BTN", lang))
        builder.button(text=Messages.get("ADMIN_GROUPS_BTN", lang))
        builder.button(text=Messages.get("ADMIN_STATS_BTN", lang))
        builder.button(text=Messages.get("ADMIN_AI_SETTINGS_BTN", lang))
    
    builder.adjust(2)
    return builder.as_markup(resize_keyboard=True)


def get_contact_keyboard(lang: str):
    keyboard = ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text=Messages.get("SHARE_CONTACT_BTN", lang), request_contact=True)]],
        resize_keyboard=True,
        one_time_keyboard=True
    )
    return keyboard

def get_language_keyboard(lang: str = "UZ"):
    builder = ReplyKeyboardBuilder()
    builder.button(text="🇺🇿 O'zbekcha")
    builder.button(text="🇺🇸 English")
    builder.button(text=Messages.get("BACK_BTN", lang))
    builder.adjust(2)
    return builder.as_markup(resize_keyboard=True)

def get_cancel_keyboard(lang: str):
    builder = ReplyKeyboardBuilder()
    builder.button(text=Messages.get("CANCEL_BTN", lang))
    return builder.as_markup(resize_keyboard=True)

def get_quizzes_keyboard(quizzes: list, lang: str):
    builder = ReplyKeyboardBuilder()
    for q in quizzes:
        builder.button(text=q['title'])
    builder.button(text=Messages.get("BACK_BTN", lang))
    builder.adjust(1)
    return builder.as_markup(resize_keyboard=True)

def get_shuffle_keyboard(lang: str):
    builder = ReplyKeyboardBuilder()
    builder.button(text=Messages.get("SHUFFLE_YES", lang))
    builder.button(text=Messages.get("SHUFFLE_NO", lang))
    builder.adjust(2)
    return builder.as_markup(resize_keyboard=True, one_time_keyboard=True)

def get_inline_shuffle_keyboard(lang: str):
    builder = InlineKeyboardBuilder()
    builder.button(text=Messages.get("SHUFFLE_YES", lang), callback_data="shuffle_yes")
    builder.button(text=Messages.get("SHUFFLE_NO", lang), callback_data="shuffle_no")
    builder.adjust(2)
    return builder.as_markup()

def get_stop_keyboard(lang: str):
    builder = ReplyKeyboardBuilder()
    builder.button(text=Messages.get("STOP_QUIZ_BTN", lang))
    return builder.as_markup(resize_keyboard=True)

def get_start_quiz_keyboard(lang: str):
    builder = ReplyKeyboardBuilder()
    builder.button(text=Messages.get("START_QUIZ_BTN", lang))
    builder.button(text=Messages.get("CANCEL_BTN", lang))
    builder.adjust(1)
    return builder.as_markup(resize_keyboard=True)

async def enable_user_menu(bot: Bot, user_id: int):
    commands = [
        types.BotCommand(command="start", description="Botni ishga tushirish / Start the bot"),
        types.BotCommand(command="set_language", description="Tilni tanlash / Select language"),
        types.BotCommand(command="help", description="Yordam / Help")
    ]
    try:
        await bot.set_my_commands(commands, scope=types.BotCommandScopeChat(chat_id=user_id))
    except Exception as e:
        logger.error(f"Failed to set user menu for {user_id}: {e}")

def get_admin_ai_keyboard(lang: str):
    builder = ReplyKeyboardBuilder()
    builder.button(text=Messages.get("ADMIN_SET_GEN_LIMIT_BTN", lang))
    builder.button(text=Messages.get("ADMIN_SET_CON_LIMIT_BTN", lang))
    builder.button(text=Messages.get("BACK_BTN", lang))
    builder.adjust(2)
    return builder.as_markup(resize_keyboard=True)
