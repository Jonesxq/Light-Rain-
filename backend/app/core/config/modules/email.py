"""Email configuration module"""

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings

class EmailSettings(BaseSettings):
    """Email configuration settings"""
    
    # SMTP Server Configuration
    EMAIL_HOST: str = Field(
        default="smtp.gmail.com",
        description="SMTP server host"
    )
    
    EMAIL_PORT: int = Field(
        default=587,
        description="SMTP server port"
    )
    
    EMAIL_HOST_USER: str = Field(
        default="",
        description="SMTP username"
    )
    
    EMAIL_HOST_PASSWORD: SecretStr = Field(
        default="",
        description="SMTP password"
    )
    
    # SSL/TLS Configuration
    EMAIL_USE_TLS: bool = Field(
        default=True,
        description="Use TLS for SMTP connection"
    )
    
    EMAIL_USE_SSL: bool = Field(
        default=False,
        description="Use SSL for SMTP connection"
    )
    
    EMAIL_SSL_CERT_REQS: str = Field(
        default="required",
        description="SSL certificate requirements (required/optional/none)"
    )
    
    # Timeout Configuration
    EMAIL_TIMEOUT: int = Field(
        default=30,
        description="SMTP connection timeout in seconds"
    )
    
    # Email Expiration
    EMAIL_EXPIRATION: int = Field(
        default=3600,
        description="Email verification code expiration time in seconds"
    )
    
    # Email From Configuration
    EMAIL_FROM_NAME: str = Field(
        default="",
        description="Email sender name"
    )
    
    EMAIL_FROM_EMAIL: str = Field(
        default="",
        description="Email sender address"
    )
    
    class Config:
        env_file = ".env"
        case_sensitive = True
        extra = "ignore"

