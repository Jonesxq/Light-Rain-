"""loggingconfigurationmodule"""

from typing import Optional
from pydantic import Field
from app.core.config.base import EnvBaseSettings

class LoggingSettings(EnvBaseSettings):
    """Loguru loggingconfigurationSet"""
    
    LOG_LEVEL: str = Field(
        default="INFO",
        description="Logging level: DEBUG, INFO, WARNING, ERROR, CRITICAL",
    )
    LOG_TO_FILE: bool = Field(
        default=False,
        description="Generate logger configuration (app/core/config/modules/logger.py)"
    )
    LOG_FILE_PATH: str = Field(
        default="logs/app.log",
        description="Generate logger configuration (app/core/config/modules/logger.py)"
    )
    LOG_TO_CONSOLE: bool = Field(
        default=True,
        description="Generate logger configuration (app/core/config/modules/logger.py)"
    )
    LOG_CONSOLE_LEVEL: str = Field(
        default="INFO",
        description="Generate logger configuration (app/core/config/modules/logger.py)"
    )
    LOG_ROTATION: Optional[str] = Field(
        default="1 day",
        description="Generate logger configuration (app/core/config/modules/logger.py)"
    )
    LOG_RETENTION_PERIOD: Optional[str] = Field(
        default="7 days",
        description="Generate logger configuration (app/core/config/modules/logger.py)"
    )

