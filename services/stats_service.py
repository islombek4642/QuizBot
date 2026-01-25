from datetime import datetime, timedelta
from typing import List, Optional, Tuple
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, desc, and_
from models.stats import UserStat, GroupStat, PointLog
from models.user import User
from core.logger import logger

class StatsService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def add_points(
        self, 
        user_id: int, 
        chat_id: Optional[int] = None, 
        action_type: str = 'correct', 
        time_taken: float = 0.0
    ) -> int:
        """
        Calculate and add points to a user (and group if applicable).
        action_type: 'correct', 'incorrect', 'timeout'
        """
        total_delta = 0
        
        # 1. Get user stats
        result = await self.db.execute(select(UserStat).filter(UserStat.user_id == user_id))
        user_stat = result.scalar_one_or_none()
        
        if not user_stat:
            user_stat = UserStat(user_id=user_id)
            self.db.add(user_stat)
            await self.db.flush()

        # 2. Base Points & Penalties
        if action_type == 'correct':
            total_delta += 10
            user_stat.total_correct += 1
            user_stat.current_streak += 1
            if user_stat.current_streak > user_stat.max_streak:
                user_stat.max_streak = user_stat.current_streak
            
            # Speed Bonus
            speed_bonus = 0
            if time_taken <= 5.0:
                speed_bonus = 15
            elif time_taken <= 10.0:
                speed_bonus = 10
            elif time_taken <= 20.0:
                speed_bonus = 5
            
            if speed_bonus > 0:
                total_delta += speed_bonus
                await self._log_points(user_id, chat_id, speed_bonus, 'bonus_speed')

            # Streak Bonus
            streak_bonus = 0
            if user_stat.current_streak == 3:
                streak_bonus = 5
            elif user_stat.current_streak == 5:
                streak_bonus = 15
            
            if streak_bonus > 0:
                total_delta += streak_bonus
                await self._log_points(user_id, chat_id, streak_bonus, 'bonus_streak')

        elif action_type == 'incorrect':
            total_delta -= 5
            user_stat.current_streak = 0
        elif action_type == 'timeout':
            total_delta -= 2
            user_stat.current_streak = 0
            
        user_stat.total_answered += 1
        user_stat.total_points += total_delta
        user_stat.last_activity = datetime.utcnow()

        # 3. Log main points
        await self._log_points(user_id, chat_id, 10 if action_type == 'correct' else total_delta, action_type)

        # 4. Update Group Stats if applicable
        if chat_id and chat_id != user_id:
            await self._update_group_stats(chat_id, total_delta)

        await self.db.commit()
        return total_delta

    async def _log_points(self, user_id: int, chat_id: Optional[int], points: int, action_type: str):
        log = PointLog(
            user_id=user_id,
            chat_id=chat_id,
            points=points,
            action_type=action_type
        )
        self.db.add(log)

    async def _update_group_stats(self, chat_id: int, delta: int):
        result = await self.db.execute(select(GroupStat).filter(GroupStat.chat_id == chat_id))
        group_stat = result.scalar_one_or_none()
        
        if not group_stat:
            group_stat = GroupStat(chat_id=chat_id)
            self.db.add(group_stat)
            await self.db.flush()
            
        group_stat.total_points += delta
        group_stat.last_activity = datetime.utcnow()
        
        # Calculate active members from PointLog (e.g., last 30 days)
        activity_threshold = datetime.utcnow() - timedelta(days=30)
        active_users_query = select(func.count(func.distinct(PointLog.user_id))).filter(
            and_(PointLog.chat_id == chat_id, PointLog.timestamp >= activity_threshold)
        )
        active_count = (await self.db.execute(active_users_query)).scalar() or 1
        
        group_stat.active_members_count = active_count
        group_stat.avg_score = group_stat.total_points / active_count if active_count > 0 else 0

    async def get_user_leaderboard(self, period: str = 'total', limit: int = 50) -> List[dict]:
        """
        period: 'daily', 'weekly', 'total'
        """
        now = datetime.utcnow()
        start_date = None
        
        if period == 'daily':
            start_date = now.replace(hour=0, minute=0, second=0, microsecond=0)
        elif period == 'weekly':
            start_date = now - timedelta(days=now.weekday())
            start_date = start_date.replace(hour=0, minute=0, second=0, microsecond=0)

        # Base query from PointLog to ensure we capture all logged points
        query = (
            select(
                PointLog.user_id,
                func.sum(PointLog.points).label('score'),
                User.full_name,
                User.username
            )
            .join(User, User.telegram_id == PointLog.user_id)
        )

        if start_date:
            query = query.filter(PointLog.timestamp >= start_date)

        query = (
            query.group_by(PointLog.user_id, User.full_name, User.username)
            .order_by(desc('score'))
            .limit(limit)
        )

        result = await self.db.execute(query)
        rows = result.all()
        
        leaderboard = []
        for i, row in enumerate(rows, 1):
            leaderboard.append({
                "rank": i,
                "user_id": row.user_id,
                "name": row.full_name or f"User {row.user_id}",
                "username": row.username,
                "score": int(row.score)
            })
        return leaderboard

    async def get_group_leaderboard(self, limit: int = 50) -> List[dict]:
        from models.group import Group
        # Sort by average score (fair for small/large groups)
        query = (
            select(
                GroupStat.chat_id,
                GroupStat.avg_score,
                Group.title,
                Group.username
            )
            .join(Group, Group.telegram_id == GroupStat.chat_id)
            .order_by(desc(GroupStat.avg_score))
            .limit(limit)
        )
        result = await self.db.execute(query)
        rows = result.all()
        
        return [{
            "rank": i,
            "chat_id": row.chat_id,
            "title": row.title or f"Group {row.chat_id}",
            "username": row.username,
            "score": round(row.avg_score, 1)
        } for i, row in enumerate(rows, 1)]

    async def get_user_rank(self, user_id: int, period: str = 'total') -> Optional[dict]:
        """Get specific user's current rank and score"""
        # This is slightly expensive for large tables, but okay for Top 50 contexts
        leaderboard = await self.get_user_leaderboard(period, limit=1000)
        for item in leaderboard:
            if item['user_id'] == user_id:
                return item
        
        # If not in top 1000, we'd need a separate count query
        return None
