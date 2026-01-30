"""CORS configurationmodule"""

from pydantic import Field
from app.core.config.base import EnvBaseSettings

class CORSSettings(EnvBaseSettings):
    """CORS (Cross-Origin Resource Sharing) configuration"""
    
    CORS_ALLOWED_ORIGINS: str = Field(
        default=["http://localhost:5173","http://127.0.0.1:5173"],
        description="Allowed CORS origins (comma-separated)",
    )
    CORS_ALLOW_CREDENTIALS: bool = Field(
        default=True,
        description="Generate CORS configuration (app/core/config/modules/cors.py)"
    )
    CORS_ALLOW_METHODS: str = Field(
        default='GET,POST,PUT,DELETE,PATCH,OPTIONS,HEAD,TRACE,CONNECT',
        description="Allowed HTTP methods (comma-separated)",
    )
    CORS_ALLOW_HEADERS: str = Field(
        default='Authorization,Content-Type,X-Language,Accept-Language',
        description="Allowed HTTP headers (comma-separated)",
    )
    CORS_EXPOSE_HEADERS: str = Field(
        default='Content-Disposition,Content-Length,Content-Type,ETag,Last-Modified',
        description="Exposed HTTP headers (comma-separated)",
    )

