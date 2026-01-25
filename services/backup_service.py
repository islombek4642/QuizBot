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

from constants.messages import Messages

async def send_backup_to_admin(bot: Bot, lang: str = "UZ"):
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
            caption = Messages.get("BACKUP_CAPTION", lang).format(
                date=datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                file=os.path.basename(backup_path),
                size=f"{file_size_mb:.2f}"
            )
            
            await bot.send_document(
                chat_id=settings.ADMIN_ID,
                document=FSInputFile(backup_path),
                caption=caption,
                parse_mode="HTML"
            )
            logger.info(f"Backup sent to admin {settings.ADMIN_ID}")
        except Exception as e:
            logger.error("Failed to send backup to admin", error=str(e))
        finally:
            if os.path.exists(backup_path):
                os.remove(backup_path)
    else:
        logger.error("Backup failed, nothing to send")

async def perform_full_restore(file_path: str):
    """
    Performs a full database restore using psql.
    WARNING: This overwrites everything.
    """
    # 1. Decompress if needed
    work_path = file_path
    if file_path.endswith(".gz"):
        work_path = file_path[:-3]
        with gzip.open(file_path, "rb") as f_in:
            with open(work_path, "wb") as f_out:
                shutil.copyfileobj(f_in, f_out)
    
    # 2. Extract connection details
    url = settings.DATABASE_URL.replace("postgresql+asyncpg://", "postgresql://")
    
    try:
        # 3. Run psql
        # We use --clean --if-exists to drop tables before creating them
        # Note: pg_dump --clean usually handles this, but we run it as a script
        process = await asyncio.create_subprocess_exec(
            "psql", url, "-f", work_path,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE
        )
        stdout, stderr = await process.communicate()
        
        success = process.returncode == 0
        if not success:
            logger.error("Full restore failed", error=stderr.decode())
        else:
            logger.info("Full restore successful")
        
        # Cleanup decompressed file if we created one
        if work_path != file_path and os.path.exists(work_path):
            os.remove(work_path)
            
        return success
    except Exception as e:
        logger.error("Exception during full restore", error=str(e))
        return False

async def perform_smart_merge(file_path: str, session):
    """
    Merges only Users and Groups from backup into the current DB.
    Returns (u_new, u_old, g_new, g_old)
    """
    from sqlalchemy import text
    from models.user import User
    from models.group import Group
    from sqlalchemy.dialects.postgresql import insert
    import re

    # 1. Decompress if needed
    work_path = file_path
    is_temp = False
    if file_path.endswith(".gz"):
        work_path = file_path[:-3]
        is_temp = True
        with gzip.open(file_path, "rb") as f_in:
            with open(work_path, "wb") as f_out:
                shutil.copyfileobj(f_in, f_out)

    stats = {"u_new": 0, "u_old": 0, "g_new": 0, "g_old": 0, "q_new": 0, "q_old": 0}

    try:
        # Read file content
        with open(work_path, "r", encoding="utf-8") as f:
            content = f.read()

        def get_data_from_dump(table_name):
            lines = content.splitlines()
            results = []
            in_block = False
            columns = []
            
            for line in lines:
                if line.startswith(f"COPY public.{table_name} "):
                    in_block = True
                    # Extract columns between (...) 
                    # Format: COPY public.users (id, telegram_id, ...) FROM stdin;
                    match = re.search(r"\((.*?)\)", line)
                    if match:
                        columns = [c.strip() for c in match.group(1).split(",")]
                    continue
                
                if in_block:
                    if line.strip() == r"\.":
                        in_block = False
                        continue
                    vals = line.split("\t")
                    row = [v if v != r"\N" else None for v in vals]
                    if columns and len(row) == len(columns):
                        results.append(dict(zip(columns, row)))
            return results

        user_data = get_data_from_dump("users")
        group_data = get_data_from_dump("groups")
        quiz_data = get_data_from_dump("quizzes")

        # Helper to safely get values with defaults
        def safe_get(d, key, default=None):
            val = d.get(key)
            return val if val is not None and val != r"\N" else default

        # Helper to parse datetime strings
        from datetime import datetime as dt
        def parse_datetime(date_str):
            if isinstance(date_str, str):
                # Handle both with and without microseconds
                for fmt in ["%Y-%m-%d %H:%M:%S.%f", "%Y-%m-%d %H:%M:%S"]:
                    try:
                        return dt.strptime(date_str, fmt)
                    except ValueError:
                        continue
            return date_str  # Already datetime or None

        # Get actual model columns
        user_columns = {c.name for c in User.__table__.columns}
        group_columns = {c.name for c in Group.__table__.columns}
        from models.quiz import Quiz
        quiz_columns = {c.name for c in Quiz.__table__.columns}

        for u in user_data:
            try:
                # Convert types safely with defaults for missing columns
                u["id"] = int(u["id"])
                u["telegram_id"] = int(u["telegram_id"])
                u["is_active"] = safe_get(u, "is_active", "t") == "t"
                
                # Only add ai_credits if it exists in the current schema
                if "ai_credits" in user_columns:
                    u["ai_credits"] = int(safe_get(u, "ai_credits", 0) or 0)
                elif "ai_credits" in u:
                    del u["ai_credits"]  # Remove if it's in backup but not in schema
                
                # Parse datetime fields
                if "created_at" in u:
                    u["created_at"] = parse_datetime(u["created_at"])
                if "updated_at" in u:
                    u["updated_at"] = parse_datetime(u["updated_at"])
                
                # Only keep columns that exist in the model
                u_filtered = {k: v for k, v in u.items() if k in user_columns}
                
                # Use insert().on_conflict_do_nothing explicitly for postgres
                stmt = insert(User).values(**u_filtered).on_conflict_do_nothing(index_elements=["telegram_id"])
                res = await session.execute(stmt)
                if res.rowcount > 0: stats["u_new"] += 1
                else: stats["u_old"] += 1
            except Exception as e:
                logger.warning(f"Failed to merge user {u.get('telegram_id')}", error=str(e))
                stats["u_old"] += 1

        for g in group_data:
            try:
                g["id"] = int(g["id"])
                g["telegram_id"] = int(g["telegram_id"])
                g["is_active"] = safe_get(g, "is_active", "t") == "t"
                
                # Parse datetime fields
                if "created_at" in g:
                    g["created_at"] = parse_datetime(g["created_at"])
                if "updated_at" in g:
                    g["updated_at"] = parse_datetime(g["updated_at"])
                
                # Only keep columns that exist in the model
                g_filtered = {k: v for k, v in g.items() if k in group_columns}
                
                stmt = insert(Group).values(**g_filtered).on_conflict_do_nothing(index_elements=["telegram_id"])
                res = await session.execute(stmt)
                if res.rowcount > 0: stats["g_new"] += 1
                else: stats["g_old"] += 1
            except Exception as e:
                logger.warning(f"Failed to merge group {g.get('telegram_id')}", error=str(e))
                stats["g_old"] += 1

        # Process Quizzes
        for q in quiz_data:
            try:
                q["id"] = int(q["id"])
                q["user_id"] = int(q["user_id"])
                q["shuffle_options"] = safe_get(q, "shuffle_options", "t") == "t"
                
                # Handle JSON column
                if "questions_json" in q and isinstance(q["questions_json"], str):
                    import json
                    # SQL dump might have escaped JSON
                    try:
                        q["questions_json"] = json.loads(q["questions_json"].replace('\\\\', '\\').replace('\\"', '"'))
                    except:
                        pass
                
                if "created_at" in q:
                    q["created_at"] = parse_datetime(q["created_at"])
                
                q_filtered = {k: v for k, v in q.items() if k in quiz_columns}
                
                # Quizzes use auto-inc primary key, but we want to keep IDs if possible?
                # Actually, for Smart Merge, we check if title+user_id combo exists to avoid dups
                # Or just use the original ID if it's not taken.
                stmt = insert(Quiz).values(**q_filtered).on_conflict_do_nothing(index_elements=["id"])
                res = await session.execute(stmt)
                if res.rowcount > 0: stats["q_new"] += 1
                else: stats["q_old"] += 1
            except Exception as e:
                logger.warning(f"Failed to merge quiz {q.get('id')}", error=str(e))
                stats["q_old"] += 1

        await session.commit()
        return stats

    except Exception as e:
        logger.error("Smart merge failed", error=str(e))
        return None
    finally:
        if is_temp and os.path.exists(work_path):
            os.remove(work_path)
