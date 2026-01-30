"""databaseconfigurationmodule"""

from pydantic import Field, PositiveInt
from app.core.config.base import EnvBaseSettings

class DatabaseSettings(EnvBaseSettings):
    """databaseconfiguration"""
    
    # database connection URL
    DATABASE_URL: str = Field(
        default="mysql://user:password@localhost:3306/official_proj_2.0_dev",
        description="Database connection URL",
    )
    
    # connectionpoolconfiguration
    ECHO: bool = Field(
        default=False,
        description="Generate database configuration (app/core/config/modules/database.py)"
    )
    POOL_PRE_PING: bool = Field(
        default=True,
        description="Generate database configuration (app/core/config/modules/database.py)"
    )
    POOL_TIMEOUT: PositiveInt = Field(
        default=30,
        description="Generate database configuration (app/core/config/modules/database.py)"
    )
    POOL_SIZE: PositiveInt = Field(
        default=6,
        description="Database connection pool size (conservative strategy: suitable for 2-core 2GB server)",
    )
    POOL_MAX_OVERFLOW: PositiveInt = Field(
        default=2,
        description="Database connection pool max overflow (conservative strategy: reduce overflow connections)",
    )

