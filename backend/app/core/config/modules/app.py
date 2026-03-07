
"""应用程序配置模块"""
from pydantic import Field
from app.core.config.base import EnvBaseSettings

class AppSettings(EnvBaseSettings):
    """应用程序设置类"""
    APP_NAME: str = Field(
        default="official_proj_2.0",
        description="应用程序名称"
    )
    APP_DESCRIPTION: str = Field(
        default="official_proj_2.0 is a FastAPI application.",
        description="应用程序描述",
    )
    APP_VERSION: str = Field(
        default="0.1.0",
        description="应用程序版本"
    )

