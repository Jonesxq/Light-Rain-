"""core/config/modules/usage.py."""
from pydantic import Field
from app.core.config.base import EnvBaseSettings


class UsageSettings(EnvBaseSettings):

    """UsageSettings ??"""
    USAGE_DEFAULT_MONTHLY_BUDGET_USD: float = Field(
        default=20.0,
        description="Default monthly budget (USD)"
    )

    USAGE_DEFAULT_DAILY_REQUEST_LIMIT: int = Field(
        default=200,
        description="Default daily request limit"
    )

    LLM_PRICING_JSON: str = Field(
        default="{}",
        description="Model pricing JSON: {model: {prompt_per_1k, completion_per_1k}}"
    )
