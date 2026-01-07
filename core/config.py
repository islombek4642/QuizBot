from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field
from typing import Optional

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    BOT_TOKEN: str
    
    # Database
    DATABASE_URL: str = Field(..., description="Async PostgreSQL connection string (postgresql+asyncpg://...)")
    
    # Redis
    REDIS_URL: str = Field("redis://localhost:6379/0")
    
    # Quiz Settings
    FILE_SIZE_LIMIT_MB: int = 5
    MAX_QUESTIONS_PER_QUIZ: int = 100
    POLL_DURATION_SECONDS: int = 30
    POLL_MAPPING_TTL_SECONDS: int = 14400  # 4 hours
    
    # Environment
    ENV: str = "production"  # development, staging, production
    DEBUG: bool = False

settings = Settings()
