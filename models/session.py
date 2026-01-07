from sqlalchemy import Column, Integer, String, BigInteger, ForeignKey, Float, Boolean, JSON
from models.base import Base, TimestampMixin

class QuizSession(Base, TimestampMixin):
    __tablename__ = "quiz_sessions"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(BigInteger, ForeignKey("users.telegram_id"), index=True, nullable=False)
    quiz_id = Column(Integer, ForeignKey("quizzes.id"), nullable=False)
    
    current_index = Column(Integer, default=0, nullable=False)
    correct_count = Column(Integer, default=0, nullable=False)
    answered_count = Column(Integer, default=0, nullable=False)
    total_questions = Column(Integer, nullable=False)
    
    start_time = Column(Float, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    
    # Store dynamic data like shuffled question IDs if needed
    session_data = Column(JSON, nullable=True)
