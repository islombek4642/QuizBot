from datetime import datetime
from typing import Optional, List
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete, func
from models.quiz import Quiz
from core.logger import logger
from core.config import settings

class QuizService:
    def __init__(self, db: AsyncSession, redis=None):
        self.db = db
        self.redis = redis
        self.MAX_TOTAL_QUIZZES = 50
        self.MAX_DAILY_SPLITS = 10

    async def save_quiz(self, user_id: int, title: str, questions: list, shuffle_options: bool) -> Quiz:
        # Check total quiz limit (Bypass for admins)
        if user_id != settings.ADMIN_ID:
            result = await self.db.execute(select(func.count(Quiz.id)).filter(Quiz.user_id == user_id))
            user_total = result.scalar()
            if user_total >= self.MAX_TOTAL_QUIZZES:
                 return None # Or raise custom exception

        quiz = Quiz(
            user_id=user_id,
            title=title,
            questions_json=questions,
            shuffle_options=shuffle_options
        )
        self.db.add(quiz)
        await self.db.commit()
        await self.db.refresh(quiz)
        logger.info("Quiz saved", user_id=user_id, quiz_id=quiz.id, title=title)
        return quiz
    
    async def is_title_taken(self, user_id: int, title: str) -> bool:
        result = await self.db.execute(
            select(Quiz).filter(Quiz.user_id == user_id, Quiz.title == title)
        )
        return result.scalar_one_or_none() is not None

    async def get_user_quizzes(self, user_id: int):
        result = await self.db.execute(
            select(Quiz).filter(Quiz.user_id == user_id).order_by(Quiz.created_at.desc())
        )
        return result.scalars().all()

    async def get_quiz(self, quiz_id: int) -> Quiz:
        result = await self.db.execute(select(Quiz).filter(Quiz.id == quiz_id))
        return result.scalar_one_or_none()

    async def delete_quiz(self, quiz_id: int, user_id: int) -> bool:
        # Import here to avoid circular dependencies
        from models.session import QuizSession
        
        # Delete related sessions first to avoid foreign key constraints
        await self.db.execute(
            delete(QuizSession).where(QuizSession.quiz_id == quiz_id)
        )
        await self.db.commit()
        
        # Now delete the quiz
        result = await self.db.execute(
            delete(Quiz).where(Quiz.id == quiz_id, Quiz.user_id == user_id)
        )
        await self.db.commit()
        success = result.rowcount > 0
        logger.info("Quiz deleted", quiz_id=quiz_id, user_id=user_id, success=success)
        return success

    async def clone_quiz(self, quiz_id: int, new_user_id: int) -> Optional[Quiz]:
        """Clone an existing quiz for a new user"""
        # Check total quiz limit for new user (Bypass for admins)
        if new_user_id != settings.ADMIN_ID:
            result = await self.db.execute(select(func.count(Quiz.id)).filter(Quiz.user_id == new_user_id))
            user_total = result.scalar()
            if user_total >= self.MAX_TOTAL_QUIZZES:
                 return None

        quiz = await self.get_quiz(quiz_id)
        if not quiz or quiz.user_id == new_user_id:
            return None
            
        # Check if title already exists for this user
        final_title = quiz.title
        if await self.is_title_taken(new_user_id, final_title):
            import time
            final_title = f"{quiz.title} ({int(time.time() % 1000)})"
            
        new_quiz = Quiz(
            user_id=new_user_id,
            title=final_title,
            questions_json=quiz.questions_json,
            shuffle_options=quiz.shuffle_options
        )
        self.db.add(new_quiz)
        await self.db.commit()
        await self.db.refresh(new_quiz)
        logger.info("Quiz cloned", from_id=quiz.id, to_id=new_quiz.id, user_id=new_user_id)
        return new_quiz

    async def get_quiz_by_id_and_user(self, quiz_id: int, user_id: int) -> Optional[Quiz]:
        """Get a specific quiz ensuring it belongs to the user."""
        result = await self.db.execute(
            select(Quiz).filter(Quiz.id == quiz_id, Quiz.user_id == user_id)
        )
        return result.scalar_one_or_none()

    async def update_quiz(self, quiz_id: int, user_id: int, title: str, questions: list) -> bool:
        """Update an existing quiz title and questions."""
        quiz = await self.get_quiz_by_id_and_user(quiz_id, user_id)
        if not quiz:
            return False
            
        quiz.title = title
        quiz.questions_json = questions
        await self.db.commit()
        logger.info("Quiz updated", quiz_id=quiz_id, user_id=user_id)
        return True

    async def check_limit(self, user_id: int) -> bool:
        """Checks if the user can create more quizzes."""
        if user_id == settings.ADMIN_ID:
            return True
            
        result = await self.db.execute(select(func.count(Quiz.id)).filter(Quiz.user_id == user_id))
        return result.scalar() < self.MAX_TOTAL_QUIZZES

    async def split_quiz(self, quiz_id: int, user_id: int, parts: int = None, size: int = None):
        """Split a quiz into multiple parts with security checks."""
        # 1. Total quiz limit check (Bypass for admins)
        if user_id != settings.ADMIN_ID:
            result = await self.db.execute(select(func.count(Quiz.id)).filter(Quiz.user_id == user_id))
            user_total = result.scalar()
            if user_total >= self.MAX_TOTAL_QUIZZES:
                 return []

        # 2. Daily split limit (via Redis)
        if self.redis:
            today = datetime.now().strftime('%Y-%m-%d')
            split_key = f"splits:{user_id}:{today}"
            current = await self.redis.get(split_key)
            if current and int(current) >= self.MAX_DAILY_SPLITS:
                logger.warning("Daily split limit reached", user_id=user_id)
                return []

        quiz = await self.get_quiz_by_id_and_user(quiz_id, user_id)
        if not quiz:
            return []
            
        questions = quiz.questions_json
        total = len(questions)
        
        # New Rule: Source quiz must have at least 20 questions
        if total < 20:
            return []
        
        if parts:
            size = (total + parts - 1) // parts
            
        if not size or size < 10: # New Rule: Each part must have >= 10 questions
            return []
            
        # Hard safety limit: max 100 parts
        if total / size > 100:
            size = (total + 99) // 100
            
        new_quizzes = []
        for i in range(0, total, size):
            chunk = questions[i:i+size]
            part_num = (i // size) + 1
            new_title = f"{quiz.title} - {part_num}-qism"
            
            new_quiz = Quiz(
                user_id=user_id,
                title=new_title,
                questions_json=chunk,
                shuffle_options=quiz.shuffle_options
            )
            self.db.add(new_quiz)
            new_quizzes.append(new_quiz)
            
        await self.db.commit()
        
        # Increment redis counter
        if self.redis:
            today = datetime.now().strftime('%Y-%m-%d')
            split_key = f"splits:{user_id}:{today}"
            await self.redis.incr(split_key)
            await self.redis.expire(split_key, 86400) # 24h

        for nq in new_quizzes:
            await self.db.refresh(nq)
            
        logger.info("Quiz split", original_id=quiz_id, new_count=len(new_quizzes), user_id=user_id)
        return new_quizzes
