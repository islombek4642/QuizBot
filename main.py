import asyncio
from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.redis import RedisStorage
from redis.asyncio import Redis

from core.config import settings
from core.logger import setup_logging, logger
from handlers import start, quiz, settings as settings_handlers, group, admin, webapp
from utils.middleware import DbSessionMiddleware, RedisMiddleware, AuthMiddleware
from services.backup_service import send_backup_to_admin
from services.monitoring_service import monitor_sessions
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

async def start_api():
    import uvicorn
    from api.main import app
    config = uvicorn.Config(app, host="0.0.0.0", port=8000, log_level="info")
    server = uvicorn.Server(config)
    await server.serve()

async def main():
    # Parse mode from CLI args first
    import sys
    mode = "all"
    if len(sys.argv) > 1:
        if "api" in sys.argv: mode = "api"
        elif "bot" in sys.argv: mode = "bot"

    # Setup structured logging
    setup_logging()
    
    if mode == "api":
        # API is run by Uvicorn externally (command: uvicorn main:app ...)
        # But if this script is called directly with 'api', we start uvicorn programmatically
        # However, for scaling we usually run 'uvicorn api.main:app' directly.
        # This block is just a safeguard or for single-node simple run.
        logger.info("Starting API Only Mode...")
        await start_api()
        return

    # Initialize Redis
    redis = Redis.from_url(settings.REDIS_URL, decode_responses=True)
    
    # Initialize bot and dispatcher
    bot = Bot(token=settings.BOT_TOKEN)
    dp = Dispatcher(storage=RedisStorage(redis=redis))
    
    # Store redis in dispatcher
    dp["redis"] = redis

    # Register Middlewares
    dp.update.outer_middleware(DbSessionMiddleware())
    dp.update.outer_middleware(RedisMiddleware(redis))
    dp.message.middleware(AuthMiddleware())
    dp.callback_query.middleware(AuthMiddleware())

    # Include routers
    dp.include_router(admin.router)
    dp.include_router(start.router)
    dp.include_router(settings_handlers.router)
    dp.include_router(webapp.router)
    dp.include_router(group.router)
    dp.include_router(quiz.router)

    # Initialize Scheduler for Backups and Monitoring
    from zoneinfo import ZoneInfo
    scheduler = AsyncIOScheduler(timezone=ZoneInfo("Asia/Tashkent"))
    
    # 1. Daily Backup
    scheduler.add_job(
        send_backup_to_admin,
        trigger=CronTrigger(hour=settings.BACKUP_SCHEDULE_HOUR, minute=settings.BACKUP_SCHEDULE_MINUTE),
        args=[bot],
        id=settings.BACKUP_JOB_ID,
        replace_existing=True
    )
    
    # 2. Global Session Monitor (Every 30 seconds)
    scheduler.add_job(
        monitor_sessions,
        trigger="interval",
        seconds=30,
        args=[bot, redis],
        id="session_monitor",
        replace_existing=True
    )
    
    scheduler.start()
    logger.info("Scheduler started (Backup + Session Monitor).")

    # Set commands only if running bot (or all)
    try:
        from aiogram.types import BotCommand, BotCommandScopeDefault, BotCommandScopeAllGroupChats
        await bot.set_my_commands([
            BotCommand(command="start", description="Botni ishga tushirish / Start bot"),
            BotCommand(command="help", description="Yordam / Help"),
            BotCommand(command="set_language", description="Tilni o'zgartirish / Set language"),
        ], scope=BotCommandScopeDefault())
        
        await bot.set_my_commands([
            BotCommand(command="quiz_stats", description="Natijalar / Leaderboard"),
            BotCommand(command="stop_quiz", description="Testni to'xtatish / Stop quiz"),
            BotCommand(command="set_language", description="Tilni sozlash / Set language"),
            BotCommand(command="create_quiz", description="Test yaratish / Create quiz"),
            BotCommand(command="quiz_help", description="Yordam / Group help"),
        ], scope=BotCommandScopeAllGroupChats())
    except Exception as e:
        logger.error("Failed to set bot commands", error=str(e))

    # Start based on mode
    if mode == "bot":
        logger.info("Starting Bot Polling Mode...", env=settings.ENV)
        try:
            await dp.start_polling(bot)
        finally:
            await redis.aclose()
            await bot.session.close()

    else: # mode == "all"
        logger.info("Starting All (Bot + API)...", env=settings.ENV)
        try:
            await asyncio.gather(
                dp.start_polling(bot),
                start_api()
            )
        finally:
            await redis.aclose()
            await bot.session.close()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Application stopped.")
