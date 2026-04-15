"""LLM 运行时公共助手：统一处理 usage 归一化与事件落库。"""

from __future__ import annotations

from typing import Any, Optional

from app.services.shared.usage import usage_service
from app.utils.llm_usage import estimate_usage


class LLMRuntimeService:
    """封装 LLM 调用后的使用量补全、成功/失败事件记录逻辑。"""

    def finalize_usage(self, llm, messages: list, output_text: str, payload: Any) -> dict:
        """提取 usage，必要时按输入输出文本估算 token。"""
        usage = usage_service.extract_usage(payload)
        if usage.get("token_missing") or usage.get("total_tokens") is None:
            usage = estimate_usage(llm, messages, output_text)
        elif usage.get("total_tokens") is None:
            usage["total_tokens"] = (usage.get("prompt_tokens") or 0) + (usage.get("completion_tokens") or 0)
        return usage

    async def record_success(
        self,
        *,
        db,
        user_id: Optional[int],
        event_type: str,
        model_name: Optional[str],
        usage: dict,
        latency_ms: Optional[int],
        metadata: Optional[dict] = None,
    ) -> None:
        """记录成功调用的 usage 与成本事件。"""
        if user_id is None:
            return
        cost_usd = usage_service.compute_cost(
            model_name,
            usage.get("prompt_tokens"),
            usage.get("completion_tokens"),
        )
        await usage_service.record_event(
            db=db,
            user_id=user_id,
            event_type=event_type,
            model_name=model_name,
            prompt_tokens=usage.get("prompt_tokens"),
            completion_tokens=usage.get("completion_tokens"),
            total_tokens=usage.get("total_tokens"),
            token_missing=bool(usage.get("token_missing")),
            latency_ms=latency_ms,
            cost_usd=cost_usd,
            success=True,
            metadata=metadata,
        )

    async def record_failure(
        self,
        *,
        db,
        user_id: Optional[int],
        event_type: str,
        model_name: Optional[str],
        error: Exception | str,
        latency_ms: Optional[int],
        metadata: Optional[dict] = None,
    ) -> None:
        """记录失败调用事件，usage 统一记为缺失。"""
        if user_id is None:
            return
        await usage_service.record_event(
            db=db,
            user_id=user_id,
            event_type=event_type,
            model_name=model_name,
            prompt_tokens=None,
            completion_tokens=None,
            total_tokens=None,
            token_missing=True,
            latency_ms=latency_ms,
            cost_usd=0.0,
            success=False,
            error_message=str(error),
            metadata=metadata,
        )


llm_runtime_service = LLMRuntimeService()
