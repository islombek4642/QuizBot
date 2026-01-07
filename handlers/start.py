from aiogram import Router, types, F
from aiogram.filters import CommandStart, Command
from constants.messages import Messages
from handlers.common import get_main_keyboard, enable_user_menu, get_contact_keyboard
from services.user_service import UserService

router = Router()
# Only handle private chats - no keyboard buttons in groups
router.message.filter(F.chat.type == "private")

@router.message(CommandStart())
@router.message(F.text.in_([Messages.get("START_BTN", "UZ"), Messages.get("START_BTN", "EN")]))
async def cmd_start(message: types.Message, user_service: UserService):
    telegram_id = message.from_user.id
    lang = await user_service.get_language(telegram_id)
    
    user = await user_service.get_or_create_user(telegram_id)
    if not user or not user.phone_number:
        await message.answer(
            Messages.get("SHARE_CONTACT_PROMPT", lang),
            reply_markup=get_contact_keyboard(lang)
        )
        return

    await enable_user_menu(message.bot, telegram_id)
    welcome_text = Messages.get("WELCOME", lang) + "\n\n" + Messages.get("FORMAT_INFO", lang)
    
    await message.answer(welcome_text, reply_markup=get_main_keyboard(lang, telegram_id))

@router.message(F.contact)
async def process_contact(message: types.Message, user_service: UserService):
    telegram_id = message.from_user.id
    contact = message.contact
    lang = await user_service.get_language(telegram_id)

    if contact.user_id != telegram_id:
        return

    await user_service.update_user(
        telegram_id=telegram_id,
        phone_number=contact.phone_number,
        full_name=f"{contact.first_name} {contact.last_name}" if contact.last_name else contact.first_name,
        username=message.from_user.username
    )

    await enable_user_menu(message.bot, telegram_id)
    await message.answer(
        Messages.get("CONTACT_SAVED", lang),
        reply_markup=get_main_keyboard(lang, telegram_id)
    )

@router.message(Command("help"))
@router.message(F.text.in_([Messages.get("HELP_BTN", "UZ"), Messages.get("HELP_BTN", "EN")]))
async def cmd_help(message: types.Message, user_service: UserService):
    telegram_id = message.from_user.id
    lang = await user_service.get_language(telegram_id)
    
    from aiogram.utils.keyboard import InlineKeyboardBuilder
    from core.config import settings

    builder = InlineKeyboardBuilder()
    if settings.ADMIN_ID != 0:
        builder.button(
            text=Messages.get("CONTACT_ADMIN_BTN", lang),
            url=f"tg://user?id={settings.ADMIN_ID}"
        )
    
    await message.answer(
        Messages.get("HELP_TEXT", lang),
        parse_mode="HTML",
        reply_markup=builder.as_markup()
    )
