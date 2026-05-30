"""使用量统计服务"""
from __future__ import annotations

import json
from datetime import datetime, timedelta
from time import perf_counter
from typing import Any, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config.settings import settings
from app.core.database import mysql_manager
from app.core.logger import logger_manager
from app.crud.usage import usage_crud
from app.models.usage import UsageEvent, UserUsageSettings

logger = logger_manager.get_logger(__name__)


class UsageService:
    """使用量统计服务：记录LLM调用、计算成本、管理用户预算等"""
    
    def __init__(self) -> None:
        """初始化使用量服务"""
        self._pricing_cache: Optional[dict[str, dict[str, float]]] = None

    def _load_pricing(self) -> dict[str, dict[str, float]]:
        """加载定价配置"""
        if self._pricing_cache is not None:
            return self._pricing_cache
        raw = getattr(settings.usage, "LLM_PRICING_JSON", "{}") or "{}"
        try:
            data = json.loads(raw)
        except Exception:
            logger.warning("Invalid LLM_PRICING_JSON, fallback to empty dict.")
            data = {}
        pricing: dict[str, dict[str, float]] = {}
        if isinstance(data, dict):
            for model, row in data.items():
                if not isinstance(row, dict):
                    continue
                prompt = row.get("prompt_per_1k") or row.get("input_per_1k") or row.get("prompt")
                completion = row.get("completion_per_1k") or row.get("output_per_1k") or row.get("completion")
                try:
                    pricing[str(model)] = {
                        "prompt_per_1k": float(prompt or 0),
                        "completion_per_1k": float(completion or 0),
                    }
                except Exception:
                    continue
        self._pricing_cache = pricing
        return pricing

    def extract_usage(self, payload: Any) -> dict:
        """从响应中提取token使用量
        
        Args:
            payload: LLM响应对象
            
        Returns:
            包含token使用量的字典
        """
        if payload is None:
            return {"prompt_tokens": None, "completion_tokens": None, "total_tokens": None, "token_missing": True}

        usage = None

        # LangChain响应对象
        if hasattr(payload, "response_metadata"):
            usage = getattr(payload, "response_metadata", {}).get("token_usage")
        if usage is None and hasattr(payload, "usage_metadata"):
            usage = getattr(payload, "usage_metadata", None)

        # 字典格式
        if usage is None and isinstance(payload, dict):
            usage = (
                payload.get("usage_metadata")
                or payload.get("token_usage")
                or payload.get("usage")
                or payload
            )

        if not isinstance(usage, dict):
            return {"prompt_tokens": None, "completion_tokens": None, "total_tokens": None, "token_missing": True}

        prompt_tokens = usage.get("prompt_tokens")
        if prompt_tokens is None:
            prompt_tokens = usage.get("input_tokens")
        completion_tokens = usage.get("completion_tokens")
        if completion_tokens is None:
            completion_tokens = usage.get("output_tokens")
        total_tokens = usage.get("total_tokens")
        if total_tokens is None:
            total_tokens = usage.get("total")

        if total_tokens is None and prompt_tokens is not None and completion_tokens is not None:
            total_tokens = prompt_tokens + completion_tokens

        token_missing = total_tokens is None and prompt_tokens is None and completion_tokens is None

        return {
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": total_tokens,
            "token_missing": token_missing,
        }

    def compute_cost(self, model: Optional[str], prompt_tokens: Optional[int], completion_tokens: Optional[int]) -> float:
        """计算调用成本（USD）
        
        Args:
            model: 模型名称
            prompt_tokens: 输入token数
            completion_tokens: 输出token数
            
        Returns:
            计算出的成本
        """
        if model is None:
            return 0.0
        if prompt_tokens is None and completion_tokens is None:
            return 0.0

        pricing = self._load_pricing()
        model_key = model.strip() if isinstance(model, str) else None
        model_pricing = pricing.get(model_key) if model_key else None
        if not model_pricing and model_key:
            model_pricing = pricing.get(model_key.lower())
        if not model_pricing:
            return 0.0

        prompt_rate = float(model_pricing.get("prompt_per_1k", 0))
        completion_rate = float(model_pricing.get("completion_per_1k", 0))

        prompt_tokens = prompt_tokens or 0
        completion_tokens = completion_tokens or 0

        cost = (prompt_tokens / 1000.0) * prompt_rate + (completion_tokens / 1000.0) * completion_rate
        return round(cost, 6)

    async def record_event(
        self,
        db: AsyncSession | None,
        *,
        user_id: int,
        event_type: str,
        model_name: Optional[str],
        prompt_tokens: Optional[int],
        completion_tokens: Optional[int],
        total_tokens: Optional[int],
        token_missing: bool,
        latency_ms: Optional[int],
        cost_usd: float,
        success: bool = True,
        error_message: Optional[str] = None,
        metadata: Optional[dict] = None,
    ) -> None:
        """记录使用量事件
        
        Args:
            db: 数据库会话
            user_id: 用户ID
            event_type: 事件类型
            model_name: 模型名称
            prompt_tokens: 输入token数
            completion_tokens: 输出token数
            total_tokens: 总token数
            token_missing: token是否缺失
            latency_ms: 延迟（毫秒）
            cost_usd: 成本（USD）
            success: 是否成功
            error_message: 错误信息
            metadata: 附加元数据
        """
        try:
            event = UsageEvent(
                user_id=user_id,
                event_type=event_type,
                model_name=model_name,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                total_tokens=total_tokens,
                token_missing=token_missing,
                latency_ms=latency_ms,
                cost_usd=cost_usd,
                success=success,
                error_message=error_message,
                event_metadata=metadata,
            )
            if db is None:
                if not mysql_manager.async_session_maker:
                    return
                async with mysql_manager.async_session_maker() as session:
                    await usage_crud.create_event(session, event)
                return
            await usage_crud.create_event(db, event)
        except Exception as exc:
            logger.warning(f"Usage event record failed: {exc}")

    async def get_or_create_settings(self, db: AsyncSession, user_id: int) -> UserUsageSettings:
        """获取或创建用户使用量设置
        
        Args:
            db: 数据库会话
            user_id: 用户ID
            
        Returns:
            用户使用量设置
        """
        row = await usage_crud.get_user_settings(db, user_id)
        if row:
            return row
        default_budget = float(settings.usage.USAGE_DEFAULT_MONTHLY_BUDGET_USD)
        default_limit = int(settings.usage.USAGE_DEFAULT_DAILY_REQUEST_LIMIT)
        return await usage_crud.upsert_user_settings(db, user_id, default_budget, default_limit)

    async def update_settings(
        self,
        db: AsyncSession | None,
        user_id: int,
        monthly_budget_usd: Optional[float],
        daily_request_limit: Optional[int],
    ) -> UserUsageSettings:
        """更新用户使用量设置
        
        Args:
            db: 数据库会话
            user_id: 用户ID
            monthly_budget_usd: 月度预算（USD）
            daily_request_limit: 每日请求限制
            
        Returns:
            更新后的用户使用量设置
        """
        row = await usage_crud.get_user_settings(db, user_id)
        default_budget = float(settings.usage.USAGE_DEFAULT_MONTHLY_BUDGET_USD)
        default_limit = int(settings.usage.USAGE_DEFAULT_DAILY_REQUEST_LIMIT)

        budget_value = monthly_budget_usd if monthly_budget_usd is not None else (row.monthly_budget_usd if row else default_budget)
        limit_value = daily_request_limit if daily_request_limit is not None else (row.daily_request_limit if row else default_limit)

        return await usage_crud.upsert_user_settings(db, user_id, float(budget_value), int(limit_value))

    def _start_of_day(self, dt: datetime) -> datetime:
        """获取一天的开始时间"""
        return datetime(dt.year, dt.month, dt.day)

    def _start_of_month(self, dt: datetime) -> datetime:
        """获取一月的开始时间"""
        return datetime(dt.year, dt.month, 1)

    async def get_budget_status(self, db: AsyncSession, user_id: int) -> dict:
        """获取预算状态
        
        Args:
            db: 数据库会话
            user_id: 用户ID
            
        Returns:
            预算状态字典
        """
        settings_row = await self.get_or_create_settings(db, user_id)
        now = datetime.utcnow()
        month_start = self._start_of_month(now)

        summary = await usage_crud.get_overview_summary(db, user_id, month_start)
        monthly_cost = float(summary.get("total_cost_usd", 0.0))
        budget = float(settings_row.monthly_budget_usd or 0.0)
        ratio = (monthly_cost / budget) if budget > 0 else 0.0

        return {
            "monthly_budget_usd": budget,
            "monthly_cost_usd": monthly_cost,
            "budget_used_ratio": round(ratio, 4),
            "is_over_budget": budget > 0 and monthly_cost > budget,
        }

    async def get_rate_status(self, db: AsyncSession, user_id: int) -> dict:
        """获取请求频率状态
        
        Args:
            db: 数据库会话
            user_id: 用户ID
            
        Returns:
            请求频率状态字典
        """
        settings_row = await self.get_or_create_settings(db, user_id)
        now = datetime.utcnow()
        day_start = self._start_of_day(now)

        summary = await usage_crud.get_overview_summary(db, user_id, day_start)
        today_requests = int(summary.get("total_requests", 0))
        limit_value = int(settings_row.daily_request_limit or 0)
        ratio = (today_requests / limit_value) if limit_value > 0 else 0.0

        return {
            "daily_request_limit": limit_value,
            "today_request_count": today_requests,
            "rate_used_ratio": round(ratio, 4),
            "is_over_limit": limit_value > 0 and today_requests > limit_value,
        }

    async def get_overview(self, db: AsyncSession, user_id: int, range_days: int) -> dict:
        """获取使用量概览
        
        Args:
            db: 数据库会话
            user_id: 用户ID
            range_days: 统计天数
            
        Returns:
            使用量概览字典
        """
        now = datetime.utcnow()
        start_at = now - timedelta(days=max(range_days, 1) - 1)
        start_at = self._start_of_day(start_at)

        summary = await usage_crud.get_overview_summary(db, user_id, start_at)
        by_model = await usage_crud.get_breakdown_by_model(db, user_id, start_at)
        by_type = await usage_crud.get_breakdown_by_type(db, user_id, start_at)
        budget_status = await self.get_budget_status(db, user_id)
        rate_status = await self.get_rate_status(db, user_id)

        return {
            **summary,
            "by_model": by_model,
            "by_type": by_type,
            "budget_status": budget_status,
            "rate_status": rate_status,
        }

    async def get_timeseries(self, db: AsyncSession, user_id: int, range_days: int) -> list[dict]:
        """获取时间序列使用量数据
        
        Args:
            db: 数据库会话
            user_id: 用户ID
            range_days: 统计天数
            
        Returns:
            时间序列数据列表
        """
        now = datetime.utcnow()
        range_days = max(range_days, 1)
        start_at = self._start_of_day(now - timedelta(days=range_days - 1))

        rows = await usage_crud.get_timeseries(db, user_id, start_at)
        row_map = {row["date"]: row for row in rows}

        series = []
        for offset in range(range_days):
            day = start_at + timedelta(days=offset)
            key = day.date().isoformat()
            row = row_map.get(key)
            if not row:
                series.append(
                    {
                        "date": key,
                        "request_count": 0,
                        "total_tokens": 0,
                        "avg_latency_ms": 0.0,
                        "total_cost_usd": 0.0,
                    }
                )
            else:
                series.append(row)
        return series


# 全局服务实例
usage_service = UsageService()


class UsageTimer:
    """使用量计时器：测量请求延迟"""
    
    def __init__(self) -> None:
        """初始化计时器"""
        self._start = perf_counter()

    def stop_ms(self) -> int:
        """停止计时并返回延迟（毫秒）"""
        return int((perf_counter() - self._start) * 1000)
