from sqlalchemy import Column, Integer, String, JSON, Boolean, BigInteger, ForeignKey
from sqlalchemy.orm import relationship
from models.base import Base, TimestampMixin

class Quiz(Base, TimestampMixin):
    __tablename__ = "quizzes"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(BigInteger, ForeignKey("users.telegram_id"), index=True, nullable=False)
    title = Column(String(255), nullable=False)
    questions_json = Column(JSON, nullable=False)
    shuffle_options = Column(Boolean, default=True, nullable=False)

    user = relationship("User", backref="quizzes")
