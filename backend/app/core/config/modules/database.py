
"""数据库配置模块"""
from pydantic import Field, PositiveInt
from app.core.config.base import EnvBaseSettings

class DatabaseSettings(EnvBaseSettings):
    """数据库设置类"""
    DATABASE_URL: str = Field(
        default="mysql://user:password@localhost:3306/official_proj_2.0_dev",
        description="数据库连接URL",
    )
    
    # 连接池配置
    ECHO: bool = Field(
        default=False,
        description="是否输出SQL语句"
    )
    POOL_PRE_PING: bool = Field(
        default=True,
        description="连接前预检查"
    )
    POOL_TIMEOUT: PositiveInt = Field(
        default=30,
        description="连接池超时时间（秒）"
    )
    POOL_SIZE: PositiveInt = Field(
        default=6,
        description="数据库连接池大小（保守策略：适合2核2GB服务器）",
    )
    POOL_MAX_OVERFLOW: PositiveInt = Field(
        default=2,
        description="数据库连接池最大溢出数（保守策略：减少溢出连接）",
    )

