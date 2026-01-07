from aiogram import Router, types, F, Bot
from aiogram.filters import Command
from constants.messages import Messages
from handlers.common import get_language_keyboard, get_main_keyboard, enable_user_menu
from services.user_service import UserService

router = Router()

@router.message(Command("set_language"))
@router.message(F.text.in_([Messages.get("SET_LANGUAGE_BTN", "UZ"), Messages.get("SET_LANGUAGE_BTN", "EN")]))
async def cmd_set_language(message: types.Message, user_service: UserService):
    telegram_id = message.from_user.id
    lang = await user_service.get_language(telegram_id)
    
    await message.answer(
        Messages.get("CHOOSE_LANGUAGE", lang),
        reply_markup=get_language_keyboard(lang)
    )

@router.message(F.text.in_(["🇺🇿 O'zbekcha", "🇺🇸 English"]))
async def process_language_text(message: types.Message, bot: Bot, user_service: UserService):
    lang = "UZ" if "O'zbekcha" in message.text else "EN"
    await user_service.update_user(message.from_user.id, language=lang)
    
    await message.answer(
        f"{Messages.get('LANGUAGE_SET', lang)}\n\n{Messages.get('SELECT_BUTTON', lang)}",
        reply_markup=get_main_keyboard(lang, message.from_user.id)
    )
    
    await enable_user_menu(bot, message.from_user.id)
