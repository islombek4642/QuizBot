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
