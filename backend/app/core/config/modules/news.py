"""新闻配置模块"""
from pydantic import Field
from app.core.config.base import EnvBaseSettings


class NewsSettings(EnvBaseSettings):
    """新闻设置类"""
    AI_NEWS_QUERY: str = Field(
        default="人工智能 OR AI OR 大模型 OR AIGC OR OpenAI OR Claude OR Gemini",
        description="AI新闻搜索关键词",
    )
    AI_NEWS_GL: str = Field(default="cn", description="Serper地区设置")
    AI_NEWS_HL: str = Field(default="zh-cn", description="Serper语言设置")
    AI_NEWS_TBS: str = Field(default="qdr:w", description="Serper时间范围设置")
    AI_NEWS_CACHE_TTL_SECONDS: int = Field(default=900, description="缓存过期时间（秒）")
    AI_NEWS_DEFAULT_LIMIT: int = Field(default=10, description="默认新闻数量限制")
