
"""日志配置模块"""
from typing import Optional
from pydantic import Field
from app.core.config.base import EnvBaseSettings

class LoggingSettings(EnvBaseSettings):
    """日志设置类"""
    LOG_LEVEL: str = Field(
        default="INFO",
        description="日志级别：DEBUG, INFO, WARNING, ERROR, CRITICAL",
    )
    LOG_TO_FILE: bool = Field(
        default=False,
        description="是否输出到文件"
    )
    LOG_FILE_PATH: str = Field(
        default="logs/app.log",
        description="日志文件路径"
    )
    LOG_TO_CONSOLE: bool = Field(
        default=True,
        description="是否输出到控制台"
    )
    LOG_CONSOLE_LEVEL: str = Field(
        default="INFO",
        description="控制台日志级别"
    )
    LOG_ROTATION: Optional[str] = Field(
        default="1 day",
        description="日志轮转周期"
    )
    LOG_RETENTION_PERIOD: Optional[str] = Field(
        default="7 days",
        description="日志保留周期"
    )

