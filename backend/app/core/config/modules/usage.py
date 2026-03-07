"""使用统计配置模块"""
from pydantic import Field
from app.core.config.base import EnvBaseSettings


class UsageSettings(EnvBaseSettings):
    """使用统计设置类"""
    USAGE_DEFAULT_MONTHLY_BUDGET_USD: float = Field(
        default=20.0,
        description="默认月度预算（美元）"
    )

    USAGE_DEFAULT_DAILY_REQUEST_LIMIT: int = Field(
        default=200,
        description="默认每日请求限制"
    )

    LLM_PRICING_JSON: str = Field(
        default="{}",
        description="模型定价JSON格式：{model: {prompt_per_1k, completion_per_1k}}"
    )
