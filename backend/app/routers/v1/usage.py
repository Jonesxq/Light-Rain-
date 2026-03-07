"""使用统计路由模块 - 提供使用情况统计和预算管理API"""
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import get_current_user
from app.models.user import User
from app.schemas.usage import (
    UsageOverviewResponse,
    UsageTimeseriesResponse,
    UserUsageSettingsResponse,
    UserUsageSettingsUpdate,
)
from app.services.usage import usage_service

router = APIRouter(prefix="/usage", tags=["Usage"])


@router.get("/overview", response_model=UsageOverviewResponse)
async def get_usage_overview(
    range_days: int = Query(30, ge=1, le=365),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """获取使用统计概览
    
    包含总请求数、Token使用量、平均延迟、费用等综合统计，以及按模型和类型分组的数据
    
    Args:
        range_days: 统计天数范围（1-365天）
        current_user: 当前登录用户
        db: 数据库会话
        
    Returns:
        UsageOverviewResponse: 使用统计概览
    """
    data = await usage_service.get_overview(db, current_user.id, range_days)
    return data


@router.get("/timeseries", response_model=UsageTimeseriesResponse)
async def get_usage_timeseries(
    range_days: int = Query(30, ge=1, le=365),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """获取使用统计时间序列数据
    
    按天统计请求数、Token使用量、平均延迟和费用
    
    Args:
        range_days: 统计天数范围（1-365天）
        current_user: 当前登录用户
        db: 数据库会话
        
    Returns:
        UsageTimeseriesResponse: 时间序列统计数据
    """
    series = await usage_service.get_timeseries(db, current_user.id, range_days)
    return {"series": series}


@router.get("/settings/me", response_model=UserUsageSettingsResponse)
async def get_usage_settings(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """获取当前用户的使用设置
    
    包括月度预算和每日请求限制
    
    Args:
        current_user: 当前登录用户
        db: 数据库会话
        
    Returns:
        UserUsageSettingsResponse: 使用设置信息
    """
    row = await usage_service.get_or_create_settings(db, current_user.id)
    return {
        "monthly_budget_usd": float(row.monthly_budget_usd),
        "daily_request_limit": int(row.daily_request_limit),
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    }


@router.put("/settings/me", response_model=UserUsageSettingsResponse)
async def update_usage_settings(
    payload: UserUsageSettingsUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """更新当前用户的使用设置
    
    支持更新月度预算和每日请求限制
    
    Args:
        payload: 使用设置更新信息
        current_user: 当前登录用户
        db: 数据库会话
        
    Returns:
        UserUsageSettingsResponse: 更新后的使用设置信息
    """
    row = await usage_service.update_settings(
        db,
        current_user.id,
        monthly_budget_usd=payload.monthly_budget_usd,
        daily_request_limit=payload.daily_request_limit,
    )
    return {
        "monthly_budget_usd": float(row.monthly_budget_usd),
        "daily_request_limit": int(row.daily_request_limit),
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    }
