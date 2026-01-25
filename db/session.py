from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from core.config import settings

# PostgreSQL driver for async operations is asyncpg
engine = create_async_engine(
    settings.DATABASE_URL,
    echo=False, # Disable echo in prod for performance
    pool_pre_ping=True,
    pool_recycle=3600,
    pool_size=20,       # Base connections
    max_overflow=10,    # Burst connections
    future=True
)

AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)

async def get_db():
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()


async def get_redis():
    from redis.asyncio import Redis
    from core.config import settings
    redis = Redis.from_url(settings.REDIS_URL, decode_responses=True)
    try:
        yield redis
    finally:
        await redis.aclose()
