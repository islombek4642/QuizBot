from typing import Any, Awaitable, Callable, Dict
from aiogram import BaseMiddleware, types
from aiogram.types import TelegramObject
from db.session import AsyncSessionLocal
from redis.asyncio import Redis
from services.user_service import UserService
from services.quiz_service import QuizService
from services.session_service import SessionService
from constants.messages import Messages
from handlers.common import get_contact_keyboard
from core.logger import logger

class DbSessionMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any],
    ) -> Any:
        async with AsyncSessionLocal() as session:
            data["db"] = session
            data["user_service"] = UserService(session)
            data["quiz_service"] = QuizService(session)
            
            # Injection for SessionService requires redis which is added by another middleware
            return await handler(event, data)

class RedisMiddleware(BaseMiddleware):
    def __init__(self, redis: Redis):
        self.redis = redis

    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any],
    ) -> Any:
        # High-level log to see if updates even arrive at the middleware
        event_type = type(event).__name__
        # In aiogram, event can be Update or the actual Telegram object
        if hasattr(event, "event"):
            logger.info("UPDATE RECEIVED", type=type(event.event).__name__)
        else:
            logger.info("UPDATE RECEIVED", type=event_type)

        data["redis"] = self.redis
        
        # Now that we have both, we can inject SessionService
        if "db" in data:
            data["session_service"] = SessionService(data["db"], self.redis)
            
        return await handler(event, data)

class AuthMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any],
    ) -> Any:
        if not isinstance(event, types.Message):
            return await handler(event, data)

        # Skip auth checks for group chats - no keyboards should appear there
        if event.chat.type in ("group", "supergroup"):
            return await handler(event, data)

        # Allow /start (and its variations) and contact sharing
        is_start_command = False
        if event.text:
            command_part = event.text.split()[0]
            if command_part == "/start" or command_part.startswith("/start@"):
                is_start_command = True
        
        if is_start_command or event.contact:
            return await handler(event, data)

        user_service: UserService = data.get("user_service")
        if not user_service:
            return await handler(event, data)

        telegram_id = event.from_user.id
        user = await user_service.get_or_create_user(telegram_id)
        
        if not user or not user.phone_number:
            lang = user.language if user else "UZ"
            logger.info("Access denied - contact sharing required", telegram_id=telegram_id)
            await event.answer(
                Messages.get("SHARE_CONTACT_PROMPT", lang),
                reply_markup=get_contact_keyboard(lang)
            )
            return

        return await handler(event, data)

