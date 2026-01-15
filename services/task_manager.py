import asyncio
from typing import Dict
from core.logger import logger

class TaskManager:
    _instance = None
    _tasks: Dict[int, asyncio.Task] = {}

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(TaskManager, cls).__new__(cls)
        return cls._instance

    def register_task(self, user_id: int, task: asyncio.Task):
        """Register a new task for a user, cancelling any existing one."""
        self.cancel_task(user_id)
        self._tasks[user_id] = task
        logger.debug(f"Registered new task for user {user_id}")
        
        # Add callback to remove from dict when done
        task.add_done_callback(lambda t: self._cleanup_task(user_id, t))

    def cancel_task(self, user_id: int):
        """Cancel the active task for a user if it exists."""
        if user_id in self._tasks:
            task = self._tasks[user_id]
            if not task.done():
                task.cancel()
                logger.debug(f"Cancelled active task for user {user_id}")
            del self._tasks[user_id]

    def _cleanup_task(self, user_id: int, task: asyncio.Task):
        """Remove task from dict if it's still the registered one."""
        if user_id in self._tasks and self._tasks[user_id] == task:
            del self._tasks[user_id]
            
task_manager = TaskManager()
