"""Redis configuration module"""

from app.core.config.base import EnvBaseSettings
from pydantic import Field


class RedisSettings(EnvBaseSettings):
    """Redis configuration"""
    
    REDIS_CONNECTION_URL: str = Field(
        default="redis://localhost:6379",
        description="Redis connection URL. Supports password: redis://:password@host:port or redis://username:password@host:port",
    )
    
    REDIS_POOL_SIZE: int = Field(
        default=5,
        description="Maximum number of connections in the Redis connection pool (Conservative strategy: suitable for 2-core 2GB server)",
    )
    
    REDIS_SOCKET_TIMEOUT: int = Field(
        default=10, 
        description="Redis socket timeout in seconds"
    )
    
    REDIS_DEFAULT_TTL: int = Field(
        default=3600, 
        description="Default cache time-to-live in seconds"
    )

