"""Celery tasks module

This module contains all Celery async task definitions.

Usage:
    from app.tasks.backup_database_task import backup_database_task
    
    # Execute task asynchronously
    result = backup_database_task.delay()
    
    # Get task result
    task_result = result.get()"""

from .backup_database_task import backup_database_task

# Export all tasks
__all__ = [
    "backup_database_task"
]

