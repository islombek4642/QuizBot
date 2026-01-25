import os
import asyncio
import subprocess
import gzip
import shutil
from datetime import datetime
from aiogram import Bot
from aiogram.types import FSInputFile
from core.config import settings
from core.logger import logger

async def create_backup():
    """
    Creates a database backup using pg_dump and compresses it with gzip.
    Returns the path to the compressed backup file.
    """
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    sql_filename = f"{settings.BACKUP_FILENAME_PREFIX}_{timestamp}.sql"
    sql_path = os.path.join(settings.BACKUP_TEMP_DIR, sql_filename)
    gz_path = f"{sql_path}.gz"
    
    # Extract connection details from DATABASE_URL
    url = settings.DATABASE_URL
    if "asyncpg" in url:
        url = url.replace("postgresql+asyncpg://", "postgresql://")
    
    try:
        # Create SQL dump
        process = await asyncio.create_subprocess_exec(
            "pg_dump", url, "-f", sql_path,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        )
        stdout, stderr = await process.communicate()
        
        if process.returncode != 0:
            logger.error("pg_dump failed", error=stderr.decode())
            if os.path.exists(sql_path): os.remove(sql_path)
            return None
            
        # Compress the SQL file
        logger.info(f"Compressing backup: {sql_path}")
        with open(sql_path, 'rb') as f_in:
            with gzip.open(gz_path, 'wb') as f_out:
                shutil.copyfileobj(f_in, f_out)
        
        # Remove original SQL file
        os.remove(sql_path)
        
        logger.info(f"Backup created and compressed: {gz_path}")
        return gz_path
    except Exception as e:
        logger.error("Failed to create backup", error=str(e))
        if os.path.exists(sql_path): os.remove(sql_path)
        return None

async def send_backup_to_admin(bot: Bot):
    """
    Creates a compressed backup and sends it to the admin.
    """
    if not settings.ADMIN_ID:
        logger.warning("ADMIN_ID not set, skipping backup send")
        return

    logger.info("Starting scheduled backup...")
    backup_path = await create_backup()
    
    if backup_path and os.path.exists(backup_path):
        try:
            file_size_mb = os.path.getsize(backup_path) / (1024 * 1024)
            caption = (
                f"📦 *Database Backup*\n"
                f"📅 Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
                f"📁 File: `{os.path.basename(backup_path)}`\n"
                f"⚖️ Size: {file_size_mb:.2f} MB"
            )
            
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
            if os.path.exists(backup_path):
                os.remove(backup_path)
    else:
        logger.error("Backup failed, nothing to send")
