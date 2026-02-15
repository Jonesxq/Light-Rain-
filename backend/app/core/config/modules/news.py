"""core/config/modules/news.py."""
from pydantic import Field
from app.core.config.base import EnvBaseSettings


class NewsSettings(EnvBaseSettings):

    """NewsSettings ??"""
    AI_NEWS_QUERY: str = Field(
        default="人工智能 OR AI OR 大模型 OR AIGC OR OpenAI OR Claude OR Gemini",
        description="Search query for AI news",
    )
    AI_NEWS_GL: str = Field(default="cn", description="Serper gl region")
    AI_NEWS_HL: str = Field(default="zh-cn", description="Serper hl language")
    AI_NEWS_TBS: str = Field(default="qdr:w", description="Serper tbs for recency")
    AI_NEWS_CACHE_TTL_SECONDS: int = Field(default=900, description="Cache TTL seconds")
    AI_NEWS_DEFAULT_LIMIT: int = Field(default=10, description="Default news limit")
