
"""JWT认证配置模块"""
from typing import Optional
from pydantic import Field, PositiveInt, SecretStr
from app.core.config.base import EnvBaseSettings

class JWTSettings(EnvBaseSettings):
    """JWT设置类"""
    JWT_SECRET_KEY: SecretStr = Field(
        ...,
        repr=False,
        description="JWT密钥"
    )
    JWT_ALGORITHM: str = Field(
        default="HS256",
        description="JWT算法"
    )
    JWT_ACCESS_TOKEN_EXPIRATION: PositiveInt = Field(
        default=1800,
        description="访问令牌过期时间（秒）"
    )
    JWT_REFRESH_TOKEN_EXPIRATION: PositiveInt = Field(
        default=86400,
        description="刷新令牌过期时间（秒）"
    )
    JWT_ISSUER: Optional[str] = Field(
        default="official_proj_2.0",
        description="JWT发行者"
    )
    JWT_AUDIENCE: Optional[str] = Field(
        default="official_proj_2.0_users",
        description="JWT受众"
    )

