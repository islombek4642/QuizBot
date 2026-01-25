from sqlalchemy import Column, BigInteger, String, Boolean
from sqlalchemy.orm import relationship
from models.base import Base, TimestampMixin

class User(Base, TimestampMixin):
    __tablename__ = "users"

    id = Column(BigInteger, primary_key=True, index=True)
    telegram_id = Column(BigInteger, unique=True, index=True, nullable=False)
    username = Column(String(255), nullable=True)
    full_name = Column(String(255), nullable=True)
    phone_number = Column(String(50), nullable=True)
    language = Column(String(10), default="UZ", nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)

    stats = relationship("UserStat", back_populates="user", uselist=False)
