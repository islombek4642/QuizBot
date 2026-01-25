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
        quiz_id: Optional[int] = None,
        action_type: str = 'correct', 
        time_taken: float = 0.0
    ) -> int:
        """
        Calculate and add points with HIGH DIFFICULTY (Hard Mode).
        Correct: +5 | Incorrect: -10 | Timeout: -5
        """
        # 1. Get user stats
        result = await self.db.execute(select(UserStat).filter(UserStat.user_id == user_id))
        user_stat = result.scalar_one_or_none()
        
        if not user_stat:
            user_stat = UserStat(user_id=user_id)
            self.db.add(user_stat)
            await self.db.flush()

        # 2. Base Calculation
        total_delta = 0
        if action_type == 'correct':
            total_delta = 5
            user_stat.total_correct += 1
            user_stat.current_streak += 1
            if user_stat.current_streak > user_stat.max_streak:
                user_stat.max_streak = user_stat.current_streak
            
            # Speed Bonus
            if time_taken <= 3.0:
                total_delta += 10
            elif time_taken <= 5.0:
                total_delta += 5

            # Streak Bonus (Every 10)
            if user_stat.current_streak > 0 and user_stat.current_streak % 10 == 0:
                total_delta += 10
        elif action_type == 'incorrect':
            total_delta = -10
            user_stat.current_streak = 0
        elif action_type == 'timeout':
            total_delta = -5
            user_stat.current_streak = 0

        # 3. Apply Daily Point Limit (Limit: 2000 pts per day to prevent grinding)
        if total_delta > 0:
            now = datetime.utcnow()
            today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
            daily_query = select(func.sum(PointLog.points)).filter(
                PointLog.user_id == user_id,
                PointLog.points > 0,
                PointLog.timestamp >= today_start
            )
            today_points = (await self.db.execute(daily_query)).scalar() or 0
            
            if today_points + total_delta > 2000:
                total_delta = max(0, 2000 - today_points)
        
        # 4. Update stats
        user_stat.total_answered += 1
        user_stat.total_points += total_delta
        user_stat.last_activity = datetime.utcnow()

        # 5. Log points ONCE (Ensures accuracy in leaderboard)
        if total_delta != 0 or action_type == 'correct':
            await self._log_points(user_id, chat_id, quiz_id, total_delta, action_type)

        # 6. Update Group Stats if applicable
        if chat_id and chat_id != user_id:
            await self._update_group_stats(chat_id, total_delta)

        await self.db.commit()
        return total_delta

    async def _log_points(self, user_id: int, chat_id: Optional[int], quiz_id: Optional[int], points: int, action_type: str):
        log = PointLog(
            user_id=user_id,
            chat_id=chat_id,
            quiz_id=quiz_id,
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
        # Note: avg_score calculation removed from hot path to avoid expensive DISTINC query.
        # Group leaderboard will now be calculated from PointLog for accuracy.

    async def get_user_leaderboard(self, period: str = 'total', limit: int = 50) -> List[dict]:
        """
        Get global user leaderboard.
        Uses LEFT JOIN to ensure all active users appear even if they have 0 points.
        """
        now = datetime.utcnow()
        start_date = None
        
        if period == 'daily':
            start_date = now.replace(hour=0, minute=0, second=0, microsecond=0)
        elif period == 'weekly':
            start_date = now - timedelta(days=now.weekday())
            start_date = start_date.replace(hour=0, minute=0, second=0, microsecond=0)

        # 1. Aggegrate points by user from PointLog
        point_sq = select(
            PointLog.user_id,
            func.sum(PointLog.points).label('total_points')
        )
        if start_date:
            point_sq = point_sq.filter(PointLog.timestamp >= start_date)
        
        point_sq = point_sq.group_by(PointLog.user_id).alias('points_agg')

        # 2. Join with User table to get names and apply is_active filter
        query = (
            select(
                User.telegram_id.label('user_id'),
                User.full_name,
                User.username,
                func.coalesce(point_sq.c.total_points, 0).label('score')
            )
            .outerjoin(point_sq, User.telegram_id == point_sq.c.user_id)
            .filter(User.is_active == True)
            .order_by(desc('score'), User.id.asc())
            .limit(limit)
        )

        result = await self.db.execute(query)
        rows = result.all()
        
        return [{
            "rank": i,
            "user_id": row.user_id,
            "name": row.full_name or f"User {row.user_id}",
            "username": row.username,
            "score": int(row.score)
        } for i, row in enumerate(rows, 1)]

    async def get_user_performance(self, user_id: int) -> List[dict]:
        """Aggregate points and stats per quiz for a specific user"""
        from models.quiz import Quiz
        
        # Subquery to aggregate PointLog by quiz_id
        stats_q = (
            select(
                PointLog.quiz_id,
                func.sum(PointLog.points).label("total_score"),
                func.count(PointLog.id).filter(PointLog.action_type == "correct").label("correct_count"),
                func.count(PointLog.id).filter(PointLog.action_type.in_(["incorrect", "timeout"])).label("error_count"),
                func.max(PointLog.timestamp).label("last_played")
            )
            .filter(PointLog.user_id == user_id)
            .group_by(PointLog.quiz_id)
            .alias("p_stats")
        )

        # Join with Quiz table for titles (Left join to include deleted/legacy quizzes)
        query = (
            select(
                stats_q.c.quiz_id,
                stats_q.c.total_score,
                stats_q.c.correct_count,
                stats_q.c.error_count,
                stats_q.c.last_played,
                Quiz.title
            )
            .outerjoin(Quiz, Quiz.id == stats_q.c.quiz_id)
            .order_by(desc(stats_q.c.last_played))
        )

        result = await self.db.execute(query)
        rows = result.all()

        return [{
            "quiz_id": row.quiz_id if row.quiz_id else 0,
            "title": row.title if row.title else "Noma'lum / O'chirilgan test",
            "score": int(row.total_score),
            "correct": row.correct_count,
            "errors": row.error_count,
            "last_played": row.last_played
        } for row in rows]

    async def get_group_leaderboard(self, limit: int = 50) -> List[dict]:
        from models.group import Group
        # Fair metric: Group Score = Average total points of Top 5 users in that group
        # This prevents large groups from winning by sheer volume and small groups from being ignored.
        
        # Subquery to get sum of points per user per group
        user_scores_sub = (
            select(
                PointLog.chat_id,
                PointLog.user_id,
                func.sum(PointLog.points).label("user_total")
            )
            .filter(PointLog.chat_id != None)
            .group_by(PointLog.chat_id, PointLog.user_id)
            .alias("user_scores")
        )
        
        # Window function to rank users within each group
        ranked_users_sub = (
            select(
                user_scores_sub.c.chat_id,
                user_scores_sub.c.user_total,
                func.row_number().over(
                    partition_by=user_scores_sub.c.chat_id,
                    order_by=desc(user_scores_sub.c.user_total)
                ).label("rnk")
            )
            .alias("ranked_users")
        )
        
        # Main query: Average of Top 5 users, joined with Group table for names
        query = (
            select(
                ranked_users_sub.c.chat_id,
                func.avg(ranked_users_sub.c.user_total).label("group_avg"),
                Group.title,
                Group.username
            )
            .join(Group, Group.telegram_id == ranked_users_sub.c.chat_id)
            .filter(ranked_users_sub.c.rnk <= 5)
            .group_by(ranked_users_sub.c.chat_id, Group.title, Group.username)
            .order_by(desc("group_avg"))
            .limit(limit)
        )
        
        result = await self.db.execute(query)
        rows = result.all()
        
        return [{
            "rank": i,
            "chat_id": row.chat_id,
            "title": row.title or f"Group {row.chat_id}",
            "username": row.username,
            "score": round(float(row.group_avg), 1)
        } for i, row in enumerate(rows, 1)]

    async def get_user_rank(self, user_id: int, period: str = 'total') -> Optional[dict]:
        """Get specific user's current rank and score with efficient SQL count"""
        # 1. Get user's own score first
        now = datetime.utcnow()
        start_date = None
        if period == 'daily':
            start_date = now.replace(hour=0, minute=0, second=0, microsecond=0)
        elif period == 'weekly':
            start_date = now - timedelta(days=now.weekday())
            start_date = start_date.replace(hour=0, minute=0, second=0, microsecond=0)

        # Get my score
        score_q = select(func.sum(PointLog.points)).filter(PointLog.user_id == user_id)
        if start_date:
            score_q = score_q.filter(PointLog.timestamp >= start_date)
        
        my_score = (await self.db.execute(score_q)).scalar() or 0
        
        # 2. Count users with higher scores (filtering is_active)
        # Subquery to get all scores
        all_scores_sub = (
            select(
                PointLog.user_id,
                func.sum(PointLog.points).label("total_score")
            )
            .join(User, User.telegram_id == PointLog.user_id)
            .filter(User.is_active == True)
        )
        if start_date:
            all_scores_sub = all_scores_sub.filter(PointLog.timestamp >= start_date)
        
        all_scores_sub = all_scores_sub.group_by(PointLog.user_id).alias("scores")

        # Count those strictly greater
        rank_q = select(func.count()).select_from(all_scores_sub).filter(all_scores_sub.c.total_score > my_score)
        rank_val = (await self.db.execute(rank_q)).scalar() + 1

        # 3. Get user metadata
        user_meta = (await self.db.execute(select(User).filter(User.telegram_id == user_id))).scalar_one_or_none()
        
        return {
            "rank": rank_val,
            "user_id": user_id,
            "name": user_meta.full_name if user_meta else f"User {user_id}",
            "username": user_meta.username if user_meta else None,
            "score": int(my_score)
        }
