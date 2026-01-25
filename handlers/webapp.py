from aiogram import Router, F, types
from aiogram.types import WebAppInfo, InlineKeyboardMarkup, InlineKeyboardButton
import time
import hmac
import hashlib
from core.config import settings
from constants.messages import Messages
from services.user_service import UserService

router = Router()

from core.logger import logger

@router.message(F.text.in_([Messages.get("WEBAPP_EDITOR_BTN", "UZ"), Messages.get("WEBAPP_EDITOR_BTN", "EN")]))
async def cmd_webapp_editor(message: types.Message, user_service: UserService):
    telegram_id = message.from_user.id
    logger.info("WebApp Editor handler triggered", user_id=telegram_id, text=message.text)
    lang = await user_service.get_language(telegram_id)
    
    # Generate Token
    timestamp = int(time.time())
    data = f"{telegram_id}:{timestamp}"
    secret = settings.BOT_TOKEN.encode()
    signature = hmac.new(secret, data.encode(), hashlib.sha256).hexdigest()
    token = f"{telegram_id}:{timestamp}:{signature}"
    
    # Construct URL
    # Ensure WEBAPP_URL doesn't end with / to avoid double slashes if needed, 
    # but usually URL params start with ? so it's fine.
    # Assuming WEBAPP_URL is like https://...
    base_url = settings.WEBAPP_URL.rstrip('/')
    signed_url = f"{base_url}?token={token}&lang={lang}"
    
    # Create Inline Keyboard with WebApp button
    markup = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(
            text=Messages.get("WEBAPP_EDITOR_BTN", lang) + " 🚀",
            web_app=WebAppInfo(url=signed_url)
        )
    ]])
    
    await message.answer(
        Messages.get("WEBAPP_PROMPT", lang),
        reply_markup=markup
    )
