"""schemas/usage.py."""
from typing import List, Optional
from pydantic import BaseModel, ConfigDict


class UsageBreakdown(BaseModel):
    """UsageBreakdown ??"""
    key: str
    request_count: int
    total_tokens: int
    total_cost_usd: float


class BudgetStatus(BaseModel):
    """BudgetStatus ??"""
    monthly_budget_usd: float
    monthly_cost_usd: float
    budget_used_ratio: float
    is_over_budget: bool


class RateStatus(BaseModel):
    """RateStatus ??"""
    daily_request_limit: int
    today_request_count: int
    rate_used_ratio: float
    is_over_limit: bool


class UsageOverviewResponse(BaseModel):
    """UsageOverviewResponse ??"""
    total_requests: int
    total_tokens: int
    avg_latency_ms: float
    total_cost_usd: float
    token_missing_count: int
    by_model: List[UsageBreakdown]
    by_type: List[UsageBreakdown]
    budget_status: BudgetStatus
    rate_status: RateStatus


class UsageTimeseriesPoint(BaseModel):
    """UsageTimeseriesPoint ??"""
    date: str
    request_count: int
    total_tokens: int
    avg_latency_ms: float
    total_cost_usd: float


class UsageTimeseriesResponse(BaseModel):
    """UsageTimeseriesResponse ??"""
    series: List[UsageTimeseriesPoint]


class UserUsageSettingsResponse(BaseModel):
    """UserUsageSettingsResponse ??"""
    monthly_budget_usd: float
    daily_request_limit: int
    updated_at: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class UserUsageSettingsUpdate(BaseModel):
    """UserUsageSettingsUpdate ??"""
    monthly_budget_usd: Optional[float] = None
    daily_request_limit: Optional[int] = None
