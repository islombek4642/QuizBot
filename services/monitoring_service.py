import time
import asyncio
import json
from datetime import datetime, timedelta
from sqlalchemy import select
from aiogram import Bot
from redis.asyncio import Redis

from core.logger import logger
from core.config import settings
from models.session import QuizSession
from db.session import AsyncSessionLocal

async def monitor_sessions(bot: Bot, redis: Redis):
    """
    Main monitoring task that runs every 30 seconds.
    Ensures all active sessions are actually moving and cleans up 'ghost' sessions.
    """
    logger.debug("Starting global session monitor scan...")
    
    # 1. Monitor Private Quizzes
    await monitor_private_sessions(bot, redis)
    
    # 2. Monitor Group Quizzes
    await monitor_group_sessions(bot, redis)
    
    logger.debug("Global session monitor scan completed.")

async def monitor_private_sessions(bot: Bot, redis: Redis):
    """
    Checks for private sessions that haven't been updated for > 35 seconds.
    Forces advancement or '3-strike' stop.
    """
    from handlers.quiz import _failsafe_advance_private_quiz
    
    threshold = datetime.utcnow() - timedelta(seconds=settings.POLL_DURATION_SECONDS + 5)
    
    async with AsyncSessionLocal() as db:
        # Find active sessions updated before the threshold
        result = await db.execute(
            select(QuizSession).filter(
                QuizSession.is_active == True,
                QuizSession.updated_at < threshold
            )
        )
        stalled_sessions = result.scalars().all()
        
        if stalled_sessions:
            logger.info(f"Monitor: Found {len(stalled_sessions)} stalled private sessions")
            
            for session in stalled_sessions:
                # We use the existing failsafe logic to handle the heavy lifting (Advance/Stop/Stats)
                # We get user language
                from services.user_service import UserService
                user_service = UserService(db)
                lang = await user_service.get_language(session.user_id)
                
                logger.info("Monitor: Forcing advancement for stalled private session", 
                            user_id=session.user_id, session_id=session.id, index=session.current_index)
                
                # We call it with a question_index check to be safe
                asyncio.create_task(
                    _failsafe_advance_private_quiz(
                        bot, 
                        session.user_id, 
                        session.id, 
                        session.current_index, 
                        redis, 
                        lang
                    )
                )

async def monitor_group_sessions(bot: Bot, redis: Redis):
    """
    Checks Redis for active group quizzes that have stalled.
    """
    from handlers.group import _advance_group_quiz, GROUP_QUIZ_KEY
    
    # Scan for group_quiz keys
    keys = await redis.keys("group_quiz:*")
    if not keys:
        return
        
    now = time.time()
    stalled_threshold = settings.POLL_DURATION_SECONDS + 5
    
    for key in keys:
        try:
            data_raw = await redis.get(key)
            if not data_raw:
                continue
            
            state = json.loads(data_raw)
            if not state.get("is_active"):
                continue
            
            # Group quizzes store 'question_start_time'
            start_time = state.get("question_start_time")
            if not start_time:
                continue
                
            elapsed = now - start_time
            if elapsed > stalled_threshold:
                chat_id = int(state["chat_id"])
                logger.info("Monitor: Forcing advancement for stalled group session", 
                            chat_id=chat_id, index=state["current_index"])
                
                asyncio.create_task(
                    _advance_group_quiz(
                        bot,
                        chat_id,
                        state["quiz_id"],
                        state["current_index"],
                        redis
                    )
                )
        except Exception as e:
            logger.error(f"Monitor: Error checking group quiz {key}", error=str(e))
