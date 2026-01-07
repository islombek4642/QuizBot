from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from models.user import User
from core.logger import logger

class UserService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_or_create_user(self, telegram_id: int, **kwargs) -> User:
        result = await self.db.execute(select(User).filter(User.telegram_id == telegram_id))
        user = result.scalar_one_or_none()
        
        if not user:
            user = User(telegram_id=telegram_id, **kwargs)
            self.db.add(user)
            await self.db.commit()
            await self.db.refresh(user)
            logger.info("New user created", telegram_id=telegram_id)
        
        return user

    async def update_user(self, telegram_id: int, **kwargs):
        user = await self.get_or_create_user(telegram_id)
        for key, value in kwargs.items():
            if hasattr(user, key):
                setattr(user, key, value)
        await self.db.commit()
        logger.info("User updated", telegram_id=telegram_id, fields=list(kwargs.keys()))
        return user

    async def get_language(self, telegram_id: int) -> str:
        user = await self.get_or_create_user(telegram_id)
        return user.language
