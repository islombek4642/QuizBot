from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete
from models.group import Group
from core.logger import logger

class GroupService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_or_create_group(self, telegram_id: int, **kwargs) -> tuple[Group, bool]:
        result = await self.db.execute(select(Group).filter(Group.telegram_id == telegram_id))
        group = result.scalar_one_or_none()
        is_new = False
        
        if not group:
            group = Group(telegram_id=telegram_id, **kwargs)
            self.db.add(group)
            await self.db.commit()
            await self.db.refresh(group)
            is_new = True
            logger.info("New group registered", telegram_id=telegram_id, title=kwargs.get('title'))
        else:
            # Update title or username if they changed
            changed = False
            for key, value in kwargs.items():
                if hasattr(group, key) and getattr(group, key) != value:
                    setattr(group, key, value)
                    changed = True
            if changed:
                await self.db.commit()
                await self.db.refresh(group)
        
        return group, is_new

    async def remove_group(self, telegram_id: int):
        await self.db.execute(delete(Group).filter(Group.telegram_id == telegram_id))
        await self.db.commit()
        logger.info("Group removed from database", telegram_id=telegram_id)

    async def update_language(self, telegram_id: int, language: str):
        result = await self.db.execute(select(Group).filter(Group.telegram_id == telegram_id))
        group = result.scalar_one_or_none()
        if group:
            group.language = language
            await self.db.commit()
            logger.info("Group language updated", telegram_id=telegram_id, language=language)
            return True
        return False

    async def get_language(self, telegram_id: int) -> str:
        result = await self.db.execute(select(Group).filter(Group.telegram_id == telegram_id))
        group = result.scalar_one_or_none()
        return group.language if group else "UZ"

    async def get_all_group_ids(self) -> list[int]:
        result = await self.db.execute(select(Group.telegram_id))
        return list(result.scalars().all())
