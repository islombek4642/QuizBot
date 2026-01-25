from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field
from typing import Optional

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    BOT_TOKEN: str
    ADMIN_ID: int = Field(0, description="Telegram ID of the admin")
    BOT_USERNAME: str = Field("", description="Bot username without @ symbol (e.g., QuizTestBot)")
    
    # Database
    DATABASE_URL: str = Field(..., description="Async PostgreSQL connection string (postgresql+asyncpg://...)")
    
    # Redis
    REDIS_URL: str = Field("redis://localhost:6379/0")
    
    # Quiz Settings
    FILE_SIZE_LIMIT_MB: int = 5
    MAX_QUESTIONS_PER_QUIZ: int = 100
    POLL_DURATION_SECONDS: int = 30
    POLL_MAPPING_TTL_SECONDS: int = 14400  # 4 hours

    # Auth
    TOKEN_TTL_SECONDS: int = 2592000  # 30 days
    INITDATA_TTL_SECONDS: int = 3600
    
    # AI Quiz Generation (Groq)
    GROQ_API_KEY: str = Field("", description="Groq API key for AI quiz generation")
    GROQ_MODEL: str = Field("llama-3.3-70b-versatile", description="Groq model to use")
    GROQ_SERVICE_TIER: str = Field("on_demand", description="Groq service tier: on_demand, flex, or auto")
    GROQ_VISION_MODEL: str = Field("meta-llama/llama-4-scout-17b-16e-instruct", description="Groq vision model for OCR")
    AI_QUIZ_COUNT: int = Field(30, description="Number of questions to generate")
    AI_GENERATION_COOLDOWN_HOURS: int = 6
    AI_CONVERSION_COOLDOWN_HOURS: int = 6
    
    # Environment
    WEBAPP_URL: str = Field("", description="URL for the Telegram WebApp Editor")
    ENV: str = "production"  # development, staging, production
    DEBUG: bool = False
    
    # Backup Settings
    BACKUP_SCHEDULE_HOUR: int = 0
    BACKUP_SCHEDULE_MINUTE: int = 0
    BACKUP_TEMP_DIR: str = "/tmp"
    BACKUP_FILENAME_PREFIX: str = "backup"
    BACKUP_JOB_ID: str = "daily_backup"
    
    # Cleanup Settings
    CLEANUP_BATCH_SIZE: int = 50
    CLEANUP_SLEEP_SECONDS: float = 0.15

settings = Settings()
