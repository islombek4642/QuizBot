import asyncio
import os
import sys
from sqlalchemy import select, update
from aiogram import Bot
from aiogram.exceptions import TelegramForbiddenError, TelegramBadRequest, TelegramRetryAfter

# Add current directory to path
sys.path.append(os.getcwd())

from core.config import settings
from db.session import AsyncSessionLocal
from models.user import User
from models.group import Group
from core.logger import logger

async def check_target(bot, target_id):
    try:
        await bot.get_chat(target_id)
        return True, None
    except TelegramForbiddenError:
        return False, "forbidden"
    except TelegramBadRequest as e:
        if "chat not found" in str(e).lower():
            return False, "not_found"
        return True, str(e)  # Some other bad request, assume active
    except TelegramRetryAfter as e:
        logger.warning(f"Rate limited. Waiting {e.retry_after} seconds...")
        await asyncio.sleep(e.retry_after)
        return await check_target(bot, target_id)
    except Exception as e:
        logger.error(f"Unexpected error checking {target_id}: {e}")
        return True, str(e) # Assume active on unknown error

async def cleanup():
    bot = Bot(token=settings.BOT_TOKEN)
    
    async with AsyncSessionLocal() as db:
        # 1. Check Users
        result = await db.execute(select(User.telegram_id).filter(User.is_active == True))
        user_ids = list(result.scalars().all())
        
        print(f"Checking {len(user_ids)} users...")
        dead_users = []
        for i, uid in enumerate(user_ids, 1):
            is_alive, reason = await check_target(bot, uid)
            if not is_alive:
                dead_users.append(uid)
                print(f"  - User {uid} is dead ({reason})")
            
            if i % 10 == 0:
                print(f"Progress: {i}/{len(user_ids)} users checked.")
            
            await asyncio.sleep(0.1) # Be gentle with API
            
        if dead_users:
            await db.execute(update(User).where(User.telegram_id.in_(dead_users)).values(is_active=False))
            print(f"Done! Marked {len(dead_users)} users as inactive.")

        # 2. Check Groups
        result = await db.execute(select(Group.telegram_id).filter(Group.is_active == True))
        group_ids = list(result.scalars().all())
        
        print(f"\nChecking {len(group_ids)} groups...")
        dead_groups = []
        for i, gid in enumerate(group_ids, 1):
            is_alive, reason = await check_target(bot, gid)
            if not is_alive:
                dead_groups.append(gid)
                print(f"  - Group {gid} is dead ({reason})")
            
            if i % 10 == 0:
                print(f"Progress: {i}/{len(group_ids)} groups checked.")
            
            await asyncio.sleep(0.1)

        if dead_groups:
            await db.execute(update(Group).where(Group.telegram_id.in_(dead_groups)).values(is_active=False))
            print(f"Done! Marked {len(dead_groups)} groups as inactive.")
            
        await db.commit()
        print("\nDatabase cleanup finished successfully!")

    await bot.session.close()

if __name__ == "__main__":
    asyncio.run(cleanup())
