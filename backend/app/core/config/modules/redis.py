
"""Redis缓存配置模块"""
from app.core.config.base import EnvBaseSettings
from pydantic import Field


class RedisSettings(EnvBaseSettings):
    """Redis设置类"""
    REDIS_CONNECTION_URL: str = Field(
        default="redis://localhost:6379",
        description="Redis连接URL，支持密码：redis://:password@host:port 或 redis://username:password@host:port",
    )
    
    REDIS_POOL_SIZE: int = Field(
        default=5,
        description="Redis连接池最大连接数（保守策略：适合2核2GB服务器）",
    )
    
    REDIS_SOCKET_TIMEOUT: int = Field(
        default=10, 
        description="Redis套接字超时时间（秒）"
    )
    
    REDIS_DEFAULT_TTL: int = Field(
        default=3600, 
        description="默认缓存过期时间（秒）"
    )

