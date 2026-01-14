from aiogram import Router, types, F, Bot
from aiogram.filters import Command
from constants.messages import Messages
from handlers.common import get_language_keyboard, get_main_keyboard, enable_user_menu
from services.user_service import UserService

router = Router()
# Only handle private chats - no keyboard buttons in groups
router.message.filter(F.chat.type == "private")

@router.message(Command("set_language"))
@router.message(F.text.in_([Messages.get("SET_LANGUAGE_BTN", "UZ"), Messages.get("SET_LANGUAGE_BTN", "EN")]))
async def cmd_set_language(message: types.Message, lang: str):
    await message.answer(
        Messages.get("CHOOSE_LANGUAGE", lang),
        reply_markup=get_language_keyboard(lang)
    )

@router.message(F.text.in_([Messages.get("BACK_BTN", "UZ"), Messages.get("BACK_BTN", "EN")]))
async def cmd_back_settings(message: types.Message, lang: str):
    telegram_id = message.from_user.id
    await message.answer(
        Messages.get("SELECT_BUTTON", lang),
        reply_markup=get_main_keyboard(lang, telegram_id)
    )

@router.message(F.text.in_(["🇺🇿 O'zbekcha", "🇺🇸 English"]))
async def process_language_text(message: types.Message, bot: Bot, user_service: UserService):
    new_lang = "UZ" if "O'zbekcha" in message.text else "EN"
    await user_service.update_user(message.from_user.id, language=new_lang)
    
    await message.answer(
        f"{Messages.get('LANGUAGE_SET', new_lang)}\n\n{Messages.get('SELECT_BUTTON', new_lang)}",
        reply_markup=get_main_keyboard(new_lang, message.from_user.id)
    )
    
    await enable_user_menu(bot, message.from_user.id)
