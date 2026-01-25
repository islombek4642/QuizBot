from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from models.user import User
from core.logger import logger

class UserService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_or_create_user(self, telegram_id: int, **kwargs) -> tuple[User, bool]:
        result = await self.db.execute(select(User).filter(User.telegram_id == telegram_id))
        user = result.scalar_one_or_none()
        is_new = False
        
        if not user:
            user = User(telegram_id=telegram_id, **kwargs)
            user.is_active = True
            self.db.add(user)
            await self.db.commit()
            await self.db.refresh(user)
            is_new = True
            logger.info("New user created", telegram_id=telegram_id)
        else:
            # Reactivate if inactive
            needs_commit = False
            if not user.is_active:
                user.is_active = True
                needs_commit = True
                logger.info("Inactive user became active", telegram_id=telegram_id)
            
            # Update missing profile info from kwargs
            if kwargs.get("full_name") and not user.full_name:
                user.full_name = kwargs["full_name"]
                needs_commit = True
            if kwargs.get("username") and not user.username:
                user.username = kwargs["username"]
                needs_commit = True
                
            if needs_commit:
                await self.db.commit()
        
        return user, is_new

    async def update_user(self, telegram_id: int, **kwargs):
        user, _ = await self.get_or_create_user(telegram_id)
        for key, value in kwargs.items():
            if hasattr(user, key):
                setattr(user, key, value)
        await self.db.commit()
        logger.info("User updated", telegram_id=telegram_id, fields=list(kwargs.keys()))
        return user

    async def get_language(self, telegram_id: int) -> str:
        user, _ = await self.get_or_create_user(telegram_id)
        return user.language
