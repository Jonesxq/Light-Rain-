"""使用统计数据库操作模块 - 提供用户使用记录和统计的CRUD操作"""
from datetime import datetime
from typing import List, Optional

from sqlalchemy import func, case
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.models.usage import UsageEvent, UserUsageSettings


class UsageCRUD:
    """使用统计CRUD操作类 - 管理用户使用记录和统计数据的数据库操作"""
    
    async def create_event(self, db: AsyncSession, event: UsageEvent) -> UsageEvent:
        """创建使用事件记录
        
        Args:
            db: 异步数据库会话
            event: 使用事件对象
            
        Returns:
            UsageEvent: 创建的事件对象
        """
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
        """获取使用概览统计
        
        Args:
            db: 异步数据库会话
            user_id: 用户ID
            start_at: 统计开始时间
            
        Returns:
            dict: 包含总请求数、总token数、平均延迟、总成本等统计信息的字典
        """
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
        """按模型分组的使用统计
        
        Args:
            db: 异步数据库会话
            user_id: 用户ID
            start_at: 统计开始时间
            
        Returns:
            List[dict]: 每个模型的使用统计列表
        """
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
        """按事件类型分组的使用统计
        
        Args:
            db: 异步数据库会话
            user_id: 用户ID
            start_at: 统计开始时间
            
        Returns:
            List[dict]: 每个事件类型的使用统计列表
        """
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
        """按日期分组的时间序列使用统计
        
        Args:
            db: 异步数据库会话
            user_id: 用户ID
            start_at: 统计开始时间
            
        Returns:
            List[dict]: 每天的使用统计列表
        """
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
        """获取用户使用设置
        
        Args:
            db: 异步数据库会话
            user_id: 用户ID
            
        Returns:
            Optional[UserUsageSettings]: 用户设置对象，如果不存在则返回None
        """
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
        """更新或创建用户使用设置
        
        Args:
            db: 异步数据库会话
            user_id: 用户ID
            monthly_budget_usd: 月度预算（美元）
            daily_request_limit: 每日请求限制
            
        Returns:
            UserUsageSettings: 更新后的设置对象
        """
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
