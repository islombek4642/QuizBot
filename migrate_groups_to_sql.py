import asyncio
import os
from sqlalchemy import select
from db.session import AsyncSessionLocal
from models.group import Group
from services.group_service import GroupService
from redis.asyncio import Redis

# Redis config from environment or default
REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379/0")

async def migrate_groups():
    print("Starting migration from Redis to SQL...")
    
    # Connect to Redis
    redis = await Redis.from_url(REDIS_URL, decode_responses=True)
    
    # Connect to DB
    async with AsyncSessionLocal() as session:
        group_service = GroupService(session)
        
        # Get all group IDs from Redis
        # Based on previous code: request was `redis.smembers("bot_groups")`
        redis_group_ids = await redis.smembers("bot_groups")
        print(f"Found {len(redis_group_ids)} groups in Redis.")
        
        migrated_count = 0
        skipped_count = 0
        
        for group_id_str in redis_group_ids:
            try:
                group_id = int(group_id_str)
                
                # Check if already exists in SQL
                existing_group, is_new = await group_service.get_or_create_group(group_id, title=f"Group {group_id}")
                
                # Try to get more info from Redis if available
                # Previous code used: `redis.hgetall(f"group_info:{group_id}")`
                group_info = await redis.hgetall(f"group_info:{group_id}")
                
                if group_info:
                    title = group_info.get("title")
                    username = group_info.get("username")
                    # language might be stored separately or in group_info? 
                    # specific handler logic: language is in `group_lang:{group_id}`?
                    # Let's check handlers/group.py logic later, but mostly title/username update is good.
                    
                    if title or username:
                        if title:
                            existing_group.title = title
                        if username:
                            existing_group.username = username
                        session.add(existing_group)
                        migrated_count += 1
                else:
                    # Just created with default name "Group {id}"
                    migrated_count += 1
                    
            except Exception as e:
                print(f"Error migrating group {group_id_str}: {e}")
                skipped_count += 1

        await session.commit()
        print(f"Migration finished. Migrated/Updated: {migrated_count}, Skipped/Error: {skipped_count}")

    await redis.close()

if __name__ == "__main__":
    try:
        asyncio.run(migrate_groups())
    except KeyboardInterrupt:
        print("Migration stopped.")
