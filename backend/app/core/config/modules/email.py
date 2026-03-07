
"""邮件配置模块"""
from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings

class EmailSettings(BaseSettings):
    """邮件设置类"""
    # SMTP服务器配置
    EMAIL_HOST: str = Field(
        default="smtp.gmail.com",
        description="SMTP服务器主机"
    )
    
    EMAIL_PORT: int = Field(
        default=587,
        description="SMTP服务器端口"
    )
    
    EMAIL_HOST_USER: str = Field(
        default="",
        description="SMTP用户名"
    )
    
    EMAIL_HOST_PASSWORD: SecretStr = Field(
        default="",
        description="SMTP密码"
    )
    
    # SSL/TLS配置
    EMAIL_USE_TLS: bool = Field(
        default=True,
        description="是否使用TLS连接"
    )
    
    EMAIL_USE_SSL: bool = Field(
        default=False,
        description="是否使用SSL连接"
    )
    
    EMAIL_SSL_CERT_REQS: str = Field(
        default="required",
        description="SSL证书要求（required/optional/none）"
    )
    
    # 超时配置
    EMAIL_TIMEOUT: int = Field(
        default=30,
        description="SMTP连接超时时间（秒）"
    )
    
    # 邮件过期时间
    EMAIL_EXPIRATION: int = Field(
        default=3600,
        description="邮箱验证码过期时间（秒）"
    )
    
    # 邮件发送者配置
    EMAIL_FROM_NAME: str = Field(
        default="",
        description="邮件发送者名称"
    )
    
    EMAIL_FROM_EMAIL: str = Field(
        default="",
        description="邮件发送者地址"
    )
    
    class Config:
        """配置类"""
        env_file = ".env"
        case_sensitive = True
        extra = "ignore"

