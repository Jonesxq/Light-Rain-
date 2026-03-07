
"""Celery异步任务配置模块"""
from app.core.config.base import EnvBaseSettings
from pydantic import Field


class CelerySettings(EnvBaseSettings):
    """Celery设置类"""
    CELERY_BROKER_URL: str = Field(
        default="redis://localhost:6379/1",
        description="Celery消息代理URL（Redis数据库1）",
    )
    
    CELERY_RESULT_BACKEND: str = Field(
        default="redis://localhost:6379/2",
        description="Celery结果存储URL（Redis数据库2）",
    )
    
    CELERY_ACCEPT_CONTENT: list[str] = Field(
        default=["json"],
        description="Celery接受的内容类型",
    )
    
    CELERY_TASK_SERIALIZER: str = Field(
        default="json",
        description="Celery任务序列化器",
    )
    
    CELERY_RESULT_SERIALIZER: str = Field(
        default="json",
        description="Celery结果序列化器",
    )
    
    CELERY_TIMEZONE: str = Field(
        default="UTC",
        description="Celery时区",
    )
    
    CELERY_ENABLE_UTC: bool = Field(
        default=True,
        description="是否启用UTC时间",
    )

