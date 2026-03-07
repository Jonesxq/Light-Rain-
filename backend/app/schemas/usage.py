"""使用统计数据验证模型模块 - 用于使用统计的请求和响应"""
from typing import List, Optional
from pydantic import BaseModel, ConfigDict


class UsageBreakdown(BaseModel):
    """使用统计分组模型 - 按模型或类型分组的统计数据"""
    key: str
    request_count: int
    total_tokens: int
    total_cost_usd: float


class BudgetStatus(BaseModel):
    """预算状态模型 - 用户月度预算使用情况"""
    monthly_budget_usd: float
    monthly_cost_usd: float
    budget_used_ratio: float
    is_over_budget: bool


class RateStatus(BaseModel):
    """速率限制状态模型 - 用户每日请求限制使用情况"""
    daily_request_limit: int
    today_request_count: int
    rate_used_ratio: float
    is_over_limit: bool


class UsageOverviewResponse(BaseModel):
    """使用统计概览响应模型 - 综合使用统计数据"""
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
    """使用统计时间序列点模型 - 单个时间点的统计数据"""
    date: str
    request_count: int
    total_tokens: int
    avg_latency_ms: float
    total_cost_usd: float


class UsageTimeseriesResponse(BaseModel):
    """使用统计时间序列响应模型 - 时间序列的统计数据"""
    series: List[UsageTimeseriesPoint]


class UserUsageSettingsResponse(BaseModel):
    """用户使用设置响应模型 - 用户预算和限制配置"""
    monthly_budget_usd: float
    daily_request_limit: int
    updated_at: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class UserUsageSettingsUpdate(BaseModel):
    """用户使用设置更新模型 - 更新用户预算和限制配置"""
    monthly_budget_usd: Optional[float] = None
    daily_request_limit: Optional[int] = None
