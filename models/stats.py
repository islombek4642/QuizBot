from sqlalchemy.orm import relationship
from models.base import Base
from datetime import datetime

class UserStat(Base):
    __tablename__ = "user_stats"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(BigInteger, ForeignKey("users.telegram_id"), unique=True, index=True)
    total_points = Column(Integer, default=0)
    current_streak = Column(Integer, default=0)
    max_streak = Column(Integer, default=0)
    quizzes_completed = Column(Integer, default=0)
    total_answered = Column(Integer, default=0)
    total_correct = Column(Integer, default=0)
    last_activity = Column(DateTime, default=datetime.utcnow)

    user = relationship("User", back_populates="stats")

class GroupStat(Base):
    __tablename__ = "group_stats"

    id = Column(Integer, primary_key=True, index=True)
    chat_id = Column(BigInteger, unique=True, index=True)
    title = Column(String, nullable=True)
    total_points = Column(Integer, default=0)
    active_members_count = Column(Integer, default=0)
    quizzes_run = Column(Integer, default=0)
    avg_score = Column(Float, default=0.0)
    last_activity = Column(DateTime, default=datetime.utcnow)

class PointLog(Base):
    __tablename__ = "point_logs"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(BigInteger, ForeignKey("users.telegram_id"), index=True)
    chat_id = Column(BigInteger, index=True, nullable=True) # group_id if in group
    points = Column(Integer, nullable=False)
    action_type = Column(String)  # 'correct', 'incorrect', 'timeout', 'bonus_speed', 'bonus_streak'
    timestamp = Column(DateTime, default=datetime.utcnow, index=True)

# Indexes for fast leaderboard querying
Index("idx_points_timestamp", PointLog.timestamp, PointLog.points)
Index("idx_points_user_timestamp", PointLog.user_id, PointLog.timestamp)
Index("idx_points_chat_timestamp", PointLog.chat_id, PointLog.timestamp)
