from sqlalchemy import Column, BigInteger, String
from models.base import Base, TimestampMixin

class Group(Base, TimestampMixin):
    __tablename__ = "groups"

    id = Column(BigInteger, primary_key=True, index=True)
    telegram_id = Column(BigInteger, unique=True, index=True, nullable=False)
    title = Column(String(255), nullable=False)
    username = Column(String(255), nullable=True)
    language = Column(String(10), default="UZ", nullable=False)
