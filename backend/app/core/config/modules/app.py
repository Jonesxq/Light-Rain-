
"""core/config/modules/app.py."""
from pydantic import Field
from app.core.config.base import EnvBaseSettings

class AppSettings(EnvBaseSettings):
    
    """AppSettings ??"""
    APP_NAME: str = Field(
        default="official_proj_2.0",
        description="Application name"
    )
    APP_DESCRIPTION: str = Field(
        default="official_proj_2.0 is a FastAPI application.",
        description="Application description",
    )
    APP_VERSION: str = Field(
        default="0.1.0",
        description="Application version"
    )

