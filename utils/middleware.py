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

        # Allow /start and contact sharing
        if event.text == "/start" or event.contact:
            return await handler(event, data)

        user_service: UserService = data.get("user_service")
        if not user_service:
            return await handler(event, data)

        telegram_id = event.from_user.id
        user = await user_service.get_or_create_user(telegram_id)
        
        if not user or not user.phone_number:
            lang = await user_service.get_language(telegram_id)
            await event.answer(
                Messages.get("SHARE_CONTACT_PROMPT", lang),
                reply_markup=get_contact_keyboard(lang)
            )
            return

        return await handler(event, data)
