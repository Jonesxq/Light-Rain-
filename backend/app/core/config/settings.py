
"""core/config/settings.py."""
from functools import cached_property
from app.core.config.modules.app import AppSettings
from app.core.config.modules.logger import LoggingSettings
from app.core.config.modules.database import DatabaseSettings
from app.core.config.modules.jwt import JWTSettings
from app.core.config.modules.email import EmailSettings
from app.core.config.modules.cors import CORSSettings
from app.core.config.modules.redis import RedisSettings
from app.core.config.modules.celery import CelerySettings
from app.core.config.modules.llm import LLMSettings
from app.core.config.modules.usage import UsageSettings
from app.core.config.modules.news import NewsSettings

class Settings:
    """Settings container."""

    @cached_property
    def app(self) -> AppSettings:
        """App settings."""
        return AppSettings()

    @cached_property
    def logging(self) -> LoggingSettings:
        """Logging settings."""
        return LoggingSettings()

    @cached_property
    def database(self) -> DatabaseSettings:
        """Database settings."""
        return DatabaseSettings()

    @cached_property
    def jwt(self) -> JWTSettings:
        """JWT settings."""
        return JWTSettings()

    @cached_property
    def email(self) -> EmailSettings:
        """Email settings."""
        return EmailSettings()

    @cached_property
    def cors(self) -> CORSSettings:
        """CORS settings."""
        return CORSSettings()

    @cached_property
    def redis(self) -> RedisSettings:
        """Redis settings."""
        return RedisSettings()

    @cached_property
    def celery(self) -> CelerySettings:
        """Celery settings."""
        return CelerySettings()

    @cached_property
    def llm(self) -> LLMSettings:  # 新增属性
        """LLM settings."""
        return LLMSettings()

    @cached_property
    def usage(self) -> UsageSettings:
        """Usage settings."""
        return UsageSettings()

    @cached_property
    def news(self) -> NewsSettings:
        """News settings."""
        return NewsSettings()


# Create a global settings instance
settings = Settings()


