
"""跨域资源共享配置模块"""
from pydantic import Field
from app.core.config.base import EnvBaseSettings

class CORSSettings(EnvBaseSettings):
    """跨域设置类"""
    CORS_ALLOWED_ORIGINS: str = Field(
        default=["http://localhost:5173","http://127.0.0.1:5173"],
        description="允许的跨域来源（逗号分隔）",
    )
    CORS_ALLOW_CREDENTIALS: bool = Field(
        default=True,
        description="是否允许携带凭证"
    )
    CORS_ALLOW_METHODS: str = Field(
        default='GET,POST,PUT,DELETE,PATCH,OPTIONS,HEAD,TRACE,CONNECT',
        description="允许的HTTP方法（逗号分隔）",
    )
    CORS_ALLOW_HEADERS: str = Field(
        default='Authorization,Content-Type,X-Language,Accept-Language',
        description="允许的HTTP请求头（逗号分隔）",
    )
    CORS_EXPOSE_HEADERS: str = Field(
        default='Content-Disposition,Content-Length,Content-Type,ETag,Last-Modified',
        description="暴露的HTTP响应头（逗号分隔）",
    )

