import time
import json
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update
from redis.asyncio import Redis
from models.session import QuizSession
from core.config import settings
from core.logger import logger

class SessionService:
    def __init__(self, db: AsyncSession, redis: Redis):
        self.db = db
        self.redis = redis

    async def create_session(self, user_id: int, quiz_id: int, total_questions: int, session_data: dict = None) -> QuizSession:
        # Deactivate any existing active sessions for this user
        await self.db.execute(
            update(QuizSession)
            .filter(QuizSession.user_id == user_id, QuizSession.is_active == True)
            .values(is_active=False)
        )
        
        session = QuizSession(
            user_id=user_id,
            quiz_id=quiz_id,
            total_questions=total_questions,
            start_time=time.time(),
            session_data=session_data
        )
        self.db.add(session)
        await self.db.commit()
        await self.db.refresh(session)
        logger.info("Quiz session created", user_id=user_id, session_id=session.id)
        return session

    async def get_active_session(self, user_id: int) -> QuizSession:
        result = await self.db.execute(
            select(QuizSession).filter(QuizSession.user_id == user_id, QuizSession.is_active == True)
        )
        return result.scalar_one_or_none()

    async def map_poll_to_session(self, poll_id: str, session_id: int):
        key = f"quizbot:poll:{poll_id}"
        await self.redis.set(key, session_id, ex=settings.POLL_MAPPING_TTL_SECONDS)

    async def get_session_by_poll(self, poll_id: str) -> QuizSession:
        key = f"quizbot:poll:{poll_id}"
        session_id = await self.redis.get(key)
        if not session_id:
            return None
        
        result = await self.db.execute(select(QuizSession).filter(QuizSession.id == int(session_id)))
        return result.scalar_one_or_none()

    async def advance_session(self, session_id: int, is_correct: bool) -> QuizSession:
        # Atomic update using SELECT FOR UPDATE
        result = await self.db.execute(
            select(QuizSession).filter(QuizSession.id == session_id).with_for_update()
        )
        session = result.scalar_one_or_none()
        
        if not session or not session.is_active:
            return None
            
        session.answered_count += 1
        if is_correct:
            session.correct_count += 1
        
        session.current_index += 1
        
        if session.current_index >= session.total_questions:
            session.is_active = False
            
        await self.db.commit()
        await self.db.refresh(session)
        return session

    async def stop_session(self, user_id: int):
        await self.db.execute(
            update(QuizSession)
            .filter(QuizSession.user_id == user_id, QuizSession.is_active == True)
            .values(is_active=False)
        )
        await self.db.commit()
        logger.info("Quiz session stopped", user_id=user_id)

    async def save_last_poll_id(self, session_id: int, message_id: int):
        # Update session_data to include last_poll_message_id
        result = await self.db.execute(
            select(QuizSession).filter(QuizSession.id == session_id).with_for_update()
        )
        session = result.scalar_one_or_none()
        if session:
            data = dict(session.session_data) if session.session_data else {}
            data['last_poll_message_id'] = message_id
            session.session_data = data
            await self.db.commit()
