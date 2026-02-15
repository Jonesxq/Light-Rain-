"""routers/v1/usage.py."""
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
    """get_usage_overview ?????"""
    data = await usage_service.get_overview(db, current_user.id, range_days)
    return data


@router.get("/timeseries", response_model=UsageTimeseriesResponse)
async def get_usage_timeseries(
    range_days: int = Query(30, ge=1, le=365),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """get_usage_timeseries ?????"""
    series = await usage_service.get_timeseries(db, current_user.id, range_days)
    return {"series": series}


@router.get("/settings/me", response_model=UserUsageSettingsResponse)
async def get_usage_settings(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """get_usage_settings ?????"""
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
    """update_usage_settings ?????"""
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
