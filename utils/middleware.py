from typing import Any, Awaitable, Callable, Dict
from aiogram import BaseMiddleware
from aiogram.types import TelegramObject
from db.session import AsyncSessionLocal
from redis.asyncio import Redis
from services.user_service import UserService
from services.quiz_service import QuizService
from services.session_service import SessionService

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
