"""crud/usage.py."""
from datetime import datetime
from typing import List, Optional

from sqlalchemy import func, case
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.models.usage import UsageEvent, UserUsageSettings


class UsageCRUD:
    """UsageCRUD ??"""
    async def create_event(self, db: AsyncSession, event: UsageEvent) -> UsageEvent:
        """create_event ?????"""
        db.add(event)
        await db.commit()
        await db.refresh(event)
        return event

    async def get_overview_summary(
        self,
        db: AsyncSession,
        user_id: int,
        start_at: datetime,
    ) -> dict:
        """get_overview_summary ?????"""
        statement = (
            select(
                func.count(UsageEvent.id),
                func.coalesce(func.sum(UsageEvent.total_tokens), 0),
                func.coalesce(func.avg(UsageEvent.latency_ms), 0),
                func.coalesce(func.sum(UsageEvent.cost_usd), 0),
                func.coalesce(func.sum(case((UsageEvent.token_missing == True, 1), else_=0)), 0),
            )
            .where(UsageEvent.user_id == user_id, UsageEvent.created_at >= start_at)
        )
        result = await db.execute(statement)
        row = result.one_or_none()
        if not row:
            return {
                "total_requests": 0,
                "total_tokens": 0,
                "avg_latency_ms": 0.0,
                "total_cost_usd": 0.0,
                "token_missing_count": 0,
            }
        total_requests, total_tokens, avg_latency, total_cost, token_missing_count = row
        return {
            "total_requests": int(total_requests or 0),
            "total_tokens": int(total_tokens or 0),
            "avg_latency_ms": float(avg_latency or 0),
            "total_cost_usd": float(total_cost or 0),
            "token_missing_count": int(token_missing_count or 0),
        }

    async def get_breakdown_by_model(
        self,
        db: AsyncSession,
        user_id: int,
        start_at: datetime,
    ) -> List[dict]:
        """get_breakdown_by_model ?????"""
        statement = (
            select(
                UsageEvent.model_name,
                func.count(UsageEvent.id),
                func.coalesce(func.sum(UsageEvent.total_tokens), 0),
                func.coalesce(func.sum(UsageEvent.cost_usd), 0),
            )
            .where(UsageEvent.user_id == user_id, UsageEvent.created_at >= start_at)
            .group_by(UsageEvent.model_name)
            .order_by(func.count(UsageEvent.id).desc())
        )
        result = await db.execute(statement)
        rows = result.all()
        payload = []
        for model_name, count, total_tokens, total_cost in rows:
            key = model_name or "(unknown)"
            payload.append(
                {
                    "key": key,
                    "request_count": int(count or 0),
                    "total_tokens": int(total_tokens or 0),
                    "total_cost_usd": float(total_cost or 0),
                }
            )
        return payload

    async def get_breakdown_by_type(
        self,
        db: AsyncSession,
        user_id: int,
        start_at: datetime,
    ) -> List[dict]:
        """get_breakdown_by_type ?????"""
        statement = (
            select(
                UsageEvent.event_type,
                func.count(UsageEvent.id),
                func.coalesce(func.sum(UsageEvent.total_tokens), 0),
                func.coalesce(func.sum(UsageEvent.cost_usd), 0),
            )
            .where(UsageEvent.user_id == user_id, UsageEvent.created_at >= start_at)
            .group_by(UsageEvent.event_type)
            .order_by(func.count(UsageEvent.id).desc())
        )
        result = await db.execute(statement)
        rows = result.all()
        payload = []
        for event_type, count, total_tokens, total_cost in rows:
            key = event_type or "(unknown)"
            payload.append(
                {
                    "key": key,
                    "request_count": int(count or 0),
                    "total_tokens": int(total_tokens or 0),
                    "total_cost_usd": float(total_cost or 0),
                }
            )
        return payload

    async def get_timeseries(
        self,
        db: AsyncSession,
        user_id: int,
        start_at: datetime,
    ) -> List[dict]:
        """get_timeseries ?????"""
        statement = (
            select(
                func.date(UsageEvent.created_at).label("day"),
                func.count(UsageEvent.id),
                func.coalesce(func.sum(UsageEvent.total_tokens), 0),
                func.coalesce(func.avg(UsageEvent.latency_ms), 0),
                func.coalesce(func.sum(UsageEvent.cost_usd), 0),
            )
            .where(UsageEvent.user_id == user_id, UsageEvent.created_at >= start_at)
            .group_by(func.date(UsageEvent.created_at))
            .order_by(func.date(UsageEvent.created_at))
        )
        result = await db.execute(statement)
        rows = result.all()
        payload = []
        for day, count, total_tokens, avg_latency, total_cost in rows:
            payload.append(
                {
                    "date": str(day),
                    "request_count": int(count or 0),
                    "total_tokens": int(total_tokens or 0),
                    "avg_latency_ms": float(avg_latency or 0),
                    "total_cost_usd": float(total_cost or 0),
                }
            )
        return payload

    async def get_user_settings(self, db: AsyncSession, user_id: int) -> Optional[UserUsageSettings]:
        """get_user_settings ?????"""
        statement = select(UserUsageSettings).where(UserUsageSettings.user_id == user_id)
        result = await db.execute(statement)
        return result.scalar_one_or_none()

    async def upsert_user_settings(
        self,
        db: AsyncSession,
        user_id: int,
        monthly_budget_usd: float,
        daily_request_limit: int,
    ) -> UserUsageSettings:
        """upsert_user_settings ?????"""
        row = await self.get_user_settings(db, user_id)
        if row is None:
            row = UserUsageSettings(
                user_id=user_id,
                monthly_budget_usd=monthly_budget_usd,
                daily_request_limit=daily_request_limit,
            )
        else:
            row.monthly_budget_usd = monthly_budget_usd
            row.daily_request_limit = daily_request_limit
            row.updated_at = datetime.utcnow()

        db.add(row)
        await db.commit()
        await db.refresh(row)
        return row


usage_crud = UsageCRUD()



