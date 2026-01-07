from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete
from models.quiz import Quiz
from core.logger import logger

class QuizService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def save_quiz(self, user_id: int, title: str, questions: list, shuffle_options: bool) -> Quiz:
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
        # Ensure we delete ONLY sessions belonging to this quiz
        await self.db.execute(
            delete(QuizSession).where(QuizSession.quiz_id == quiz_id)
        )
        await self.db.commit() # Commit session deletion separately for safety
        
        # Now delete the quiz
        result = await self.db.execute(
            delete(Quiz).where(Quiz.id == quiz_id, Quiz.user_id == user_id)
        )
        await self.db.commit()
        success = result.rowcount > 0
        logger.info("Quiz deleted", quiz_id=quiz_id, user_id=user_id, success=success)
        return success
