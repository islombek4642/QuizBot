import os
import asyncio
import subprocess
from datetime import datetime
from aiogram import Bot
from aiogram.types import FSInputFile
from core.config import settings
from core.logger import logger

async def create_backup():
    """
    Creates a database backup using pg_dump.
    Returns the path to the backup file.
    """
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_filename = f"{settings.BACKUP_FILENAME_PREFIX}_{timestamp}.sql"
    backup_path = os.path.join(settings.BACKUP_TEMP_DIR, backup_filename)
    
    # Extract connection details from DATABASE_URL
    # Format: postgresql+asyncpg://user:password@host:port/dbname
    url = settings.DATABASE_URL
    if "asyncpg" in url:
        url = url.replace("postgresql+asyncpg://", "postgresql://")
    
    try:
        # We use pg_dump with the connection string directly
        # PGPASSWORD environment variable is used to avoid interactive prompt
        # But pg_dump also supports connection URI
        
        process = await asyncio.create_subprocess_exec(
            "pg_dump", url, "-f", backup_path,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        )
        stdout, stderr = await process.communicate()
        
        if process.returncode != 0:
            logger.error("pg_dump failed", error=stderr.decode())
            return None
            
        logger.info(f"Backup created successfully: {backup_path}")
        return backup_path
    except Exception as e:
        logger.error("Failed to create backup", error=str(e))
        return None

async def send_backup_to_admin(bot: Bot):
    """
    Creates a backup and sends it to the admin.
    """
    if not settings.ADMIN_ID:
        logger.warning("ADMIN_ID not set, skipping backup send")
        return

    logger.info("Starting scheduled backup...")
    backup_path = await create_backup()
    
    if backup_path and os.path.exists(backup_path):
        try:
            caption = f"📦 *Daily Backup*\n📅 Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n📁 File: {os.path.basename(backup_path)}"
            
            await bot.send_document(
                chat_id=settings.ADMIN_ID,
                document=FSInputFile(backup_path),
                caption=caption,
                parse_mode="Markdown"
            )
            logger.info(f"Backup sent to admin {settings.ADMIN_ID}")
        except Exception as e:
            logger.error("Failed to send backup to admin", error=str(e))
        finally:
            # Clean up the temporary file
            if os.path.exists(backup_path):
                os.remove(backup_path)
    else:
        logger.error("Backup failed, nothing to send")
