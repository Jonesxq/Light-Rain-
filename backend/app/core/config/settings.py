
"""全局设置管理模块"""
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
    """全局设置容器类
    使用 cached_property 实现配置的懒加载，提高性能
    """

    @cached_property
    def app(self) -> AppSettings:
        """应用程序设置"""
        return AppSettings()

    @cached_property
    def logging(self) -> LoggingSettings:
        """日志设置"""
        return LoggingSettings()

    @cached_property
    def database(self) -> DatabaseSettings:
        """数据库设置"""
        return DatabaseSettings()

    @cached_property
    def jwt(self) -> JWTSettings:
        """JWT 认证设置"""
        return JWTSettings()

    @cached_property
    def email(self) -> EmailSettings:
        """邮件设置"""
        return EmailSettings()

    @cached_property
    def cors(self) -> CORSSettings:
        """跨域资源共享设置"""
        return CORSSettings()

    @cached_property
    def redis(self) -> RedisSettings:
        """Redis 缓存设置"""
        return RedisSettings()

    @cached_property
    def celery(self) -> CelerySettings:
        """Celery 异步任务设置"""
        return CelerySettings()

    @cached_property
    def llm(self) -> LLMSettings:
        """大语言模型设置"""
        return LLMSettings()

    @cached_property
    def usage(self) -> UsageSettings:
        """使用统计设置"""
        return UsageSettings()

    @cached_property
    def news(self) -> NewsSettings:
        """新闻设置"""
        return NewsSettings()


# 创建全局设置实例
settings = Settings()


