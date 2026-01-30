"""Celery configuration module"""

from app.core.config.base import EnvBaseSettings
from pydantic import Field


class CelerySettings(EnvBaseSettings):
    """Celery configuration"""
    
    CELERY_BROKER_URL: str = Field(
        default="redis://localhost:6379/1",
        description="Celery broker URL (Redis DB 1)",
    )
    
    CELERY_RESULT_BACKEND: str = Field(
        default="redis://localhost:6379/2",
        description="Celery result backend URL (Redis DB 2)",
    )
    
    CELERY_ACCEPT_CONTENT: list[str] = Field(
        default=["json"],
        description="Accepted content types for Celery",
    )
    
    CELERY_TASK_SERIALIZER: str = Field(
        default="json",
        description="Task serializer for Celery",
    )
    
    CELERY_RESULT_SERIALIZER: str = Field(
        default="json",
        description="Result serializer for Celery",
    )
    
    CELERY_TIMEZONE: str = Field(
        default="UTC",
        description="Timezone for Celery",
    )
    
    CELERY_ENABLE_UTC: bool = Field(
        default=True,
        description="Enable UTC for Celery",
    )

