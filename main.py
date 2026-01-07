import asyncio
from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.redis import RedisStorage
from redis.asyncio import Redis

from core.config import settings
from core.logger import setup_logging, logger
from handlers import start, quiz, settings as settings_handlers, group
from utils.middleware import DbSessionMiddleware, RedisMiddleware, AuthMiddleware

async def main():
    # Setup structured logging
    setup_logging()
    
    # Initialize Redis
    redis = Redis.from_url(settings.REDIS_URL, decode_responses=True)
    
    # Initialize bot and dispatcher with Redis storage
    bot = Bot(token=settings.BOT_TOKEN)
    dp = Dispatcher(storage=RedisStorage(redis=redis))
    
    # Store redis in dispatcher for access in handlers
    dp["redis"] = redis


    # Set bot descriptions
    try:
        await bot.set_my_description(
            "Assalomu alaykum! Bu bot Word (.docx) faylidagi testlarni Telegram poll (quiz) ko'rinishiga o'tkazib beradi.\n\n"
            "Hello! This bot converts tests from Word (.docx) files into Telegram polls (quiz mode)."
        )
        await bot.set_my_short_description("Word (.docx) testlarini Poll ga aylantiruvchi bot.")
    except Exception as e:
        logger.error("Failed to set bot description", error=str(e))

    # Register Middlewares
    dp.update.outer_middleware(DbSessionMiddleware())
    dp.update.outer_middleware(RedisMiddleware(redis))
    dp.message.middleware(AuthMiddleware())

    # Include routers
    dp.include_router(group.router)  # Group router first for my_chat_member events
    dp.include_router(start.router)
    dp.include_router(settings_handlers.router)
    dp.include_router(quiz.router)

    # Set bot commands
    try:
        from aiogram.types import BotCommand, BotCommandScopeDefault, BotCommandScopeAllGroupChats
        # Default commands (Private)
        await bot.set_my_commands([
            BotCommand(command="start", description="Botni ishga tushirish / Start bot"),
            BotCommand(command="help", description="Yordam / Help"),
            BotCommand(command="set_language", description="Tilni o'zgartirish / Set language"),
        ], scope=BotCommandScopeDefault())
        
        # Group commands
        await bot.set_my_commands([
            BotCommand(command="quiz_stats", description="Natijalar / Leaderboard"),
            BotCommand(command="stop_quiz", description="Testni to'xtatish / Stop quiz"),
            BotCommand(command="set_language", description="Tilni sozlash / Set language"),
            BotCommand(command="create_quiz", description="Test yaratish / Create quiz"),
            BotCommand(command="quiz_help", description="Yordam / Group help"),
        ], scope=BotCommandScopeAllGroupChats())
    except Exception as e:
        logger.error("Failed to set bot commands", error=str(e))

    # Start polling
    logger.info("Starting QuizBot (Production Refactored)...", env=settings.ENV)
    try:
        await dp.start_polling(bot)
    finally:
        await redis.close()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Bot stopped.")
