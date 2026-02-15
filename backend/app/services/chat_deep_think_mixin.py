"""Deep-think chat helpers."""

import json
from typing import AsyncGenerator, List, Optional

from langchain_core.messages import HumanMessage, SystemMessage, BaseMessage
from sqlalchemy.ext.asyncio import AsyncSession

from app.constant.prompts import DEEP_THINK_PLAN_PROMPT, DEEP_THINK_ANSWER_PROMPT
from app.core.logger import logger_manager
from app.crud.chat import chat_crud
from app.models.chat import ChatMessage
from app.services.usage import usage_service, UsageTimer
from app.utils.chat_history import history_to_payload, history_to_text
from app.utils.json_utils import parse_json_obj
from app.utils.llm_usage import estimate_usage

logger = logger_manager.get_logger(__name__)


class ChatDeepThinkMixin:
    """Deep-think mixin."""

    async def _build_reasoning_plan(
        self,
        db: AsyncSession,
        user_id: int,
        session_id: int,
        question: str,
        chat_history: List[BaseMessage],
        model: Optional[str],
    ) -> dict:
        """Generate a reasoning plan as JSON (internal only)."""
        base_question = (question or "").strip()
        history_text = history_to_text(chat_history)
        user_content = f"用户问题：{base_question}"
        if history_text:
            user_content += f"\n\n对话上下文：\n{history_text}"

        resolved = await self._resolve_user_llm_config(db, user_id, model)
        llm = self._get_llm(
            resolved["model"],
            api_key=resolved["api_key"],
            api_base_url=resolved["api_base_url"],
            temperature=0.2,
        )
        messages = [
            SystemMessage(content=DEEP_THINK_PLAN_PROMPT),
            HumanMessage(content=user_content),
        ]
        timer = UsageTimer()
        try:
            response = await llm.ainvoke(messages)
            latency_ms = timer.stop_ms()
            usage = usage_service.extract_usage(response)
            if usage.get("total_tokens") is None:
                usage = estimate_usage(llm, messages, getattr(response, "content", "") or "")
            cost_usd = usage_service.compute_cost(
                llm.model_name,
                usage.get("prompt_tokens"),
                usage.get("completion_tokens"),
            )
            await usage_service.record_event(
                db,
                user_id=user_id,
                event_type="deep_think_plan",
                model_name=llm.model_name,
                prompt_tokens=usage.get("prompt_tokens"),
                completion_tokens=usage.get("completion_tokens"),
                total_tokens=usage.get("total_tokens"),
                token_missing=bool(usage.get("token_missing")),
                latency_ms=latency_ms,
                cost_usd=cost_usd,
                success=True,
                metadata={"session_id": session_id},
            )
            raw = getattr(response, "content", "") or ""
            plan = parse_json_obj(raw)
            if plan:
                return plan
            return {"goal": base_question, "steps": [], "raw": raw.strip()}
        except Exception as exc:
            try:
                latency_ms = timer.stop_ms()
            except Exception:
                latency_ms = None
            try:
                await usage_service.record_event(
                    db,
                    user_id=user_id,
                    event_type="deep_think_plan",
                    model_name=None,
                    prompt_tokens=None,
                    completion_tokens=None,
                    total_tokens=None,
                    token_missing=True,
                    latency_ms=latency_ms,
                    cost_usd=0.0,
                    success=False,
                    error_message=str(exc),
                    metadata={"session_id": session_id},
                )
            except Exception:
                pass
            logger.warning(f"Deep think plan generation failed: {exc}")
            return {"goal": base_question, "steps": []}

    async def _deep_think_answer(
        self,
        db: AsyncSession,
        user_id: int,
        session_id: int,
        question: str,
        chat_history: List[BaseMessage],
        model: Optional[str],
        disclaimer_codes: Optional[list[str]] = None,
        risk_tags: Optional[list[str]] = None,
    ) -> ChatMessage:
        """Non-streaming deep think answer."""
        plan = await self._build_reasoning_plan(db, user_id, session_id, question, chat_history, model)
        try:
            plan_text = json.dumps(plan, ensure_ascii=False)
        except Exception:
            plan_text = str(plan)

        temp_context = await self._get_temp_context(db, user_id, question)
        user_payload = f"用户问题：{question}\n\n【推理计划】\n{plan_text}\n\n请不要直接输出以上计划。"
        if temp_context:
            user_payload += f"\n\n【临时资料】\n{temp_context}"

        resolved = await self._resolve_user_llm_config(db, user_id, model)
        llm = self._get_llm(
            resolved["model"],
            api_key=resolved["api_key"],
            api_base_url=resolved["api_base_url"],
            temperature=0.2,
        )
        system_prompt = DEEP_THINK_ANSWER_PROMPT
        messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=user_payload),
        ]
        timer = UsageTimer()
        response = await llm.ainvoke(messages)
        latency_ms = timer.stop_ms()
        ai_content = getattr(response, "content", "") or ""
        usage = usage_service.extract_usage(response)
        if usage.get("total_tokens") is None:
            usage = estimate_usage(llm, messages, ai_content)
        cost_usd = usage_service.compute_cost(
            llm.model_name,
            usage.get("prompt_tokens"),
            usage.get("completion_tokens"),
        )
        await usage_service.record_event(
            db,
            user_id=user_id,
            event_type="deep_think_answer",
            model_name=llm.model_name,
            prompt_tokens=usage.get("prompt_tokens"),
            completion_tokens=usage.get("completion_tokens"),
            total_tokens=usage.get("total_tokens"),
            token_missing=bool(usage.get("token_missing")),
            latency_ms=latency_ms,
            cost_usd=cost_usd,
            success=True,
            metadata={"session_id": session_id},
        )

        ai_msg = await chat_crud.create_message(
            db,
            session_id=session_id,
            role="assistant",
            content=ai_content,
            model_name=llm.model_name,
            token_count=usage.get("total_tokens") or 0,
            disclaimer_codes=disclaimer_codes or [],
            risk_tags=risk_tags or [],
        )
        await self._save_prompt_snapshot(
            db=db,
            message_id=ai_msg.id,
            user_id=user_id,
            session_id=session_id,
            mode="deep_think",
            payload={
                "system_prompt": system_prompt,
                "user_input": question,
                "chat_history": history_to_payload(chat_history),
                "deep_think": {"plan": plan},
                "temp_context": temp_context,
                "model_name": llm.model_name,
            },
        )
        return ai_msg

    async def _stream_deep_think(
        self,
        db: AsyncSession,
        user_id: int,
        session_id: int,
        input_text: str,
        model: Optional[str],
        chat_history: List[BaseMessage],
        user_message_id: Optional[int] = None,
        disclaimer_codes: Optional[list[str]] = None,
        risk_tags: Optional[list[str]] = None,
    ) -> AsyncGenerator[str, None]:
        """Streaming deep think answer."""
        yield f"data: {json.dumps({'event': 'stage', 'stage': 'plan', 'message': '分析问题'})}\n\n"
        plan = await self._build_reasoning_plan(db, user_id, session_id, input_text, chat_history, model)
        try:
            plan_text = json.dumps(plan, ensure_ascii=False)
        except Exception:
            plan_text = str(plan)

        temp_context = await self._get_temp_context(db, user_id, input_text)
        user_payload = f"用户问题：{input_text}\n\n【推理计划】\n{plan_text}\n\n请不要直接输出以上计划。"
        if temp_context:
            user_payload += f"\n\n【临时资料】\n{temp_context}"

        yield f"data: {json.dumps({'event': 'stage', 'stage': 'synthesize', 'message': '整理回答'})}\n\n"
        resolved = await self._resolve_user_llm_config(db, user_id, model)
        llm = self._get_llm(
            resolved["model"],
            streaming=True,
            api_key=resolved["api_key"],
            api_base_url=resolved["api_base_url"],
            temperature=0.2,
        )
        system_prompt = DEEP_THINK_ANSWER_PROMPT
        messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=user_payload),
        ]

        full_content = ""
        timer = UsageTimer()
        async for chunk in llm.astream(messages):
            token = getattr(chunk, "content", "")
            if not token:
                continue
            full_content += token
            yield f"data: {json.dumps({'content': token})}\n\n"

        latency_ms = timer.stop_ms()
        usage = estimate_usage(llm, messages, full_content)
        total_tokens = usage.get("total_tokens") or 0
        cost_usd = usage_service.compute_cost(
            resolved["model"],
            usage.get("prompt_tokens"),
            usage.get("completion_tokens"),
        )
        await usage_service.record_event(
            db,
            user_id=user_id,
            event_type="deep_think_answer",
            model_name=resolved["model"],
            prompt_tokens=usage.get("prompt_tokens"),
            completion_tokens=usage.get("completion_tokens"),
            total_tokens=usage.get("total_tokens"),
            token_missing=bool(usage.get("token_missing")),
            latency_ms=latency_ms,
            cost_usd=cost_usd,
            success=True,
            metadata={"session_id": session_id},
        )

        ai_msg = await chat_crud.create_message(
            db,
            session_id=session_id,
            role="assistant",
            content=full_content,
            model_name=resolved["model"],
            token_count=total_tokens,
            disclaimer_codes=disclaimer_codes or [],
            risk_tags=risk_tags or [],
        )
        await self._save_prompt_snapshot(
            db=db,
            message_id=ai_msg.id,
            user_id=user_id,
            session_id=session_id,
            mode="deep_think_stream",
            payload={
                "system_prompt": system_prompt,
                "user_input": input_text,
                "chat_history": history_to_payload(chat_history),
                "deep_think": {"plan": plan},
                "temp_context": temp_context,
                "model_name": resolved["model"],
            },
        )

        payload = {
            "event": "done",
            "message": {
                "id": ai_msg.id,
                "session_id": session_id,
                "role": "assistant",
                "content": ai_msg.content,
                "model_name": resolved["model"],
                "token_count": ai_msg.token_count,
                "created_at": ai_msg.created_at.isoformat(),
                "disclaimers": ai_msg.disclaimers,
                "risk_tags": ai_msg.risk_tags,
            },
            "user_message_id": user_message_id,
        }
        yield f"data: {json.dumps(payload)}\n\n"
