
import asyncio
import sys
import os

# Add project root to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import text
from db.session import AsyncSessionLocal
from models.stats import UserStat, GroupStat, PointLog
from core.logger import logger

async def reset_statistics():
    print("⚠️  WARNING: This will RESET ALL LEADERBOARD STATISTICS (User pts, Group pts, Point Logs).")
    print("Users will keep their accounts and quizzes, but scores will be 0.")
    confirm = input("Type 'CONFIRM' to proceed: ")
    
    if confirm != "CONFIRM":
        print("Operation cancelled.")
        return

    async with AsyncSessionLocal() as session:
        try:
            print("Cleaning PointLog table...")
            await session.execute(text("TRUNCATE TABLE point_logs RESTART IDENTITY CASCADE"))
            
            print("Cleaning UserStat table...")
            await session.execute(text("TRUNCATE TABLE user_stats RESTART IDENTITY CASCADE"))
            
            print("Cleaning GroupStat table...")
            await session.execute(text("TRUNCATE TABLE group_stats RESTART IDENTITY CASCADE"))
            
            await session.commit()
            print("✅ All statistics have been reset successfully.")
            
        except Exception as e:
            await session.rollback()
            print(f"❌ Error resetting statistics: {e}")
            logger.error(f"Error resetting statistics: {e}")

if __name__ == "__main__":
    if os.name == 'nt':
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(reset_statistics())
