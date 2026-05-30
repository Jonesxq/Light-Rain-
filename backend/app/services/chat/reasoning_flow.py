"""深度思考与深度检索聊天流程。"""

from __future__ import annotations

import asyncio
import json
from typing import AsyncGenerator, List, Optional

from langchain_community.utilities import GoogleSerperAPIWrapper
from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage

from app.constant.prompts import (
    DEEP_SEARCH_ANSWER_PROMPT,
    DEEP_SEARCH_QUERY_PROMPT,
    DEEP_THINK_ANSWER_PROMPT,
    DEEP_THINK_PLAN_PROMPT,
)
from app.core.config.settings import settings
from app.core.logger import logger_manager
from app.crud.chat import chat_crud
from app.models.chat import ChatMessage
from app.services.shared.llm_runtime import llm_runtime_service
from app.services.shared.usage import UsageTimer
from app.utils.chat_history import history_to_payload, history_to_text
from app.utils.chat_web import build_search_context, fetch_web_sources, strip_source_content
from app.utils.json_utils import parse_json_list, parse_json_obj

logger = logger_manager.get_logger(__name__)


class ChatReasoningFlow:
    """负责 deep think 规划与 deep search 执行。"""

    def __init__(self, service):
        self.service = service

    async def _build_reasoning_plan(
        self,
        db,
        user_id: int,
        session_id: int,
        question: str,
        chat_history: List[BaseMessage],
        model: Optional[str],
    ) -> dict:
        base_question = (question or "").strip()
        history_text = history_to_text(chat_history)
        user_content = f"用户问题：{base_question}"
        if history_text:
            user_content += f"\n\n对话上下文：\n{history_text}"

        resolved = await self.service._resolve_user_llm_config(db, user_id, model)
        llm = self.service._get_llm(
            resolved["model"],
            api_key=resolved["api_key"],
            api_base_url=resolved["api_base_url"],
            temperature=0.2,
        )
        messages = [SystemMessage(content=DEEP_THINK_PLAN_PROMPT), HumanMessage(content=user_content)]
        timer = UsageTimer()
        try:
            response = await llm.ainvoke(messages)
            latency_ms = timer.stop_ms()
            usage = llm_runtime_service.finalize_usage(
                llm=llm,
                messages=messages,
                output_text=getattr(response, "content", "") or "",
                payload=response,
            )
            await llm_runtime_service.record_success(
                db=db,
                user_id=user_id,
                event_type="deep_think_plan",
                model_name=llm.model_name,
                usage=usage,
                latency_ms=latency_ms,
                metadata={"session_id": session_id},
            )
            raw = getattr(response, "content", "") or ""
            plan = parse_json_obj(raw)
            return plan or {"goal": base_question, "steps": [], "raw": raw.strip()}
        except Exception as exc:
            latency_ms = timer.stop_ms()
            await llm_runtime_service.record_failure(
                db=db,
                user_id=user_id,
                event_type="deep_think_plan",
                model_name=None,
                error=exc,
                latency_ms=latency_ms,
                metadata={"session_id": session_id},
            )
            logger.warning(f"Deep-think plan generation failed: {exc}")
            return {"goal": base_question, "steps": []}

    async def _build_search_queries(
        self,
        db,
        user_id: int,
        session_id: int,
        question: str,
        chat_history: List[BaseMessage],
        model: Optional[str],
    ) -> List[str]:
        base_question = (question or "").strip()
        if not base_question:
            return []

        history_text = history_to_text(chat_history)
        user_content = f"用户问题：{base_question}"
        if history_text:
            user_content += f"\n\n对话上下文：\n{history_text}"

        resolved = await self.service._resolve_user_llm_config(db, user_id, model)
        llm = self.service._get_llm(
            resolved["model"],
            api_key=resolved["api_key"],
            api_base_url=resolved["api_base_url"],
        )
        messages = [SystemMessage(content=DEEP_SEARCH_QUERY_PROMPT), HumanMessage(content=user_content)]
        timer = UsageTimer()
        try:
            response = await llm.ainvoke(messages)
            latency_ms = timer.stop_ms()
            usage = llm_runtime_service.finalize_usage(
                llm=llm,
                messages=messages,
                output_text=getattr(response, "content", "") or "",
                payload=response,
            )
            queries = parse_json_list(getattr(response, "content", "") or "") or [base_question]
            queries = queries[:4]
            await llm_runtime_service.record_success(
                db=db,
                user_id=user_id,
                event_type="deep_search_query",
                model_name=llm.model_name,
                usage=usage,
                latency_ms=latency_ms,
                metadata={"session_id": session_id, "query_count": len(queries)},
            )
            return queries
        except Exception as exc:
            latency_ms = timer.stop_ms()
            await llm_runtime_service.record_failure(
                db=db,
                user_id=user_id,
                event_type="deep_search_query",
                model_name=None,
                error=exc,
                latency_ms=latency_ms,
                metadata={"session_id": session_id},
            )
            logger.warning(f"Deep-search query generation failed: {exc}")
            return [base_question]

    async def _search_web(self, queries: List[str], max_results: int = 8) -> List[dict]:
        if not settings.llm.SERPER_API_KEY:
            raise ValueError("搜索不可用：未配置 SERPER_API_KEY")
        if not queries:
            return []

        wrapper = GoogleSerperAPIWrapper(
            serper_api_key=settings.llm.SERPER_API_KEY,
            gl=getattr(settings.news, "AI_NEWS_GL", "cn"),
            hl=getattr(settings.news, "AI_NEWS_HL", "zh-cn"),
        )
        tasks = [wrapper.aresults(query, num=6, search_type="search") for query in queries]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        sources: List[dict] = []
        seen = set()
        for result in results:
            if isinstance(result, Exception):
                continue
            for item in (result or {}).get("organic", [])[:6]:
                url = item.get("link") or item.get("url")
                if not url or url in seen:
                    continue
                seen.add(url)
                sources.append(
                    {
                        "title": item.get("title") or "网页来源",
                        "url": url,
                        "snippet": item.get("snippet") or "",
                        "source_type": "web",
                    }
                )
                if len(sources) >= max_results:
                    break
            if len(sources) >= max_results:
                break
        return sources

    async def _deep_think_answer(
        self,
        db,
        user_id: int,
        session_id: int,
        question: str,
        chat_history: List[BaseMessage],
        model: Optional[str],
        disclaimer_codes: Optional[list[str]] = None,
        risk_tags: Optional[list[str]] = None,
    ) -> ChatMessage:
        plan = await self._build_reasoning_plan(db, user_id, session_id, question, chat_history, model)
        plan_text = json.dumps(plan, ensure_ascii=False)
        temp_context = await self.service._get_temp_context(db, user_id, question)
        user_payload = f"用户问题：{question}\n\n【推理计划】\n{plan_text}\n\n请不要直接输出以上计划。"
        if temp_context:
            user_payload += f"\n\n【临时资料】\n{temp_context}"

        resolved = await self.service._resolve_user_llm_config(db, user_id, model)
        llm = self.service._get_llm(
            resolved["model"],
            api_key=resolved["api_key"],
            api_base_url=resolved["api_base_url"],
            temperature=0.2,
        )
        messages = [SystemMessage(content=DEEP_THINK_ANSWER_PROMPT), HumanMessage(content=user_payload)]
        timer = UsageTimer()
        response = await llm.ainvoke(messages)
        latency_ms = timer.stop_ms()
        ai_content = getattr(response, "content", "") or ""
        usage = llm_runtime_service.finalize_usage(llm=llm, messages=messages, output_text=ai_content, payload=response)
        await llm_runtime_service.record_success(
            db=db,
            user_id=user_id,
            event_type="deep_think_answer",
            model_name=llm.model_name,
            usage=usage,
            latency_ms=latency_ms,
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
        await self.service._save_prompt_snapshot(
            db=db,
            message_id=ai_msg.id,
            user_id=user_id,
            session_id=session_id,
            mode="deep_think",
            payload={
                "system_prompt": DEEP_THINK_ANSWER_PROMPT,
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
        db,
        user_id: int,
        session_id: int,
        input_text: str,
        model: Optional[str],
        chat_history: List[BaseMessage],
        user_message_id: Optional[int] = None,
        disclaimer_codes: Optional[list[str]] = None,
        risk_tags: Optional[list[str]] = None,
    ) -> AsyncGenerator[str, None]:
        yield f"data: {json.dumps({'event': 'stage', 'stage': 'plan', 'message': '分析问题'})}\n\n"
        plan = await self._build_reasoning_plan(db, user_id, session_id, input_text, chat_history, model)
        plan_text = json.dumps(plan, ensure_ascii=False)

        temp_context = await self.service._get_temp_context(db, user_id, input_text)
        user_payload = f"用户问题：{input_text}\n\n【推理计划】\n{plan_text}\n\n请不要直接输出以上计划。"
        if temp_context:
            user_payload += f"\n\n【临时资料】\n{temp_context}"

        yield f"data: {json.dumps({'event': 'stage', 'stage': 'synthesize', 'message': '整理回答'})}\n\n"
        resolved = await self.service._resolve_user_llm_config(db, user_id, model)
        llm = self.service._get_llm(
            resolved["model"],
            streaming=True,
            api_key=resolved["api_key"],
            api_base_url=resolved["api_base_url"],
            temperature=0.2,
        )
        messages = [SystemMessage(content=DEEP_THINK_ANSWER_PROMPT), HumanMessage(content=user_payload)]

        full_content = ""
        timer = UsageTimer()
        async for chunk in llm.astream(messages):
            token = getattr(chunk, "content", "")
            if not token:
                continue
            full_content += token
            yield f"data: {json.dumps({'content': token})}\n\n"

        latency_ms = timer.stop_ms()
        usage = llm_runtime_service.finalize_usage(llm=llm, messages=messages, output_text=full_content, payload={})
        await llm_runtime_service.record_success(
            db=db,
            user_id=user_id,
            event_type="deep_think_answer",
            model_name=resolved["model"],
            usage=usage,
            latency_ms=latency_ms,
            metadata={"session_id": session_id},
        )

        ai_msg = await chat_crud.create_message(
            db,
            session_id=session_id,
            role="assistant",
            content=full_content,
            model_name=resolved["model"],
            token_count=usage.get("total_tokens") or 0,
            disclaimer_codes=disclaimer_codes or [],
            risk_tags=risk_tags or [],
        )
        await self.service._save_prompt_snapshot(
            db=db,
            message_id=ai_msg.id,
            user_id=user_id,
            session_id=session_id,
            mode="deep_think_stream",
            payload={
                "system_prompt": DEEP_THINK_ANSWER_PROMPT,
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
                "model_name": ai_msg.model_name,
                "token_count": ai_msg.token_count,
                "created_at": ai_msg.created_at.isoformat(),
                "disclaimers": ai_msg.disclaimers,
                "risk_tags": ai_msg.risk_tags,
            },
            "user_message_id": user_message_id,
        }
        yield f"data: {json.dumps(payload)}\n\n"

    async def _deep_search_answer(
        self,
        db,
        user_id: int,
        session_id: int,
        question: str,
        chat_history: List[BaseMessage],
        model: Optional[str],
        deep_think: bool = False,
        disclaimer_codes: Optional[list[str]] = None,
        risk_tags: Optional[list[str]] = None,
    ) -> ChatMessage:
        plan = await self._build_reasoning_plan(db, user_id, session_id, question, chat_history, model)
        queries = await self._build_search_queries(db, user_id, session_id, question, chat_history, model)
        sources = await self._search_web(queries)
        enriched_sources = await fetch_web_sources(sources, top_n=4)
        context = build_search_context(enriched_sources)
        temp_context = await self.service._get_temp_context(db, user_id, question)
        user_payload = (
            f"用户问题：{question}\n\n"
            f"【思考计划】\n{json.dumps(plan, ensure_ascii=False)}\n\n"
            f"【检索资料】\n{context or '暂无可用资料'}\n\n"
            "请不要直接输出以上计划。"
        )
        if temp_context:
            user_payload += f"\n\n【临时资料】\n{temp_context}"

        resolved = await self.service._resolve_user_llm_config(db, user_id, model)
        llm = self.service._get_llm(
            resolved["model"],
            api_key=resolved["api_key"],
            api_base_url=resolved["api_base_url"],
            temperature=0.2 if deep_think else 0.3,
        )
        messages = [SystemMessage(content=DEEP_SEARCH_ANSWER_PROMPT), HumanMessage(content=user_payload)]
        timer = UsageTimer()
        response = await llm.ainvoke(messages)
        latency_ms = timer.stop_ms()
        ai_content = getattr(response, "content", "") or ""
        usage = llm_runtime_service.finalize_usage(llm=llm, messages=messages, output_text=ai_content, payload=response)
        await llm_runtime_service.record_success(
            db=db,
            user_id=user_id,
            event_type="deep_search_answer",
            model_name=llm.model_name,
            usage=usage,
            latency_ms=latency_ms,
            metadata={"session_id": session_id, "query_count": len(queries)},
        )

        store_sources = strip_source_content(enriched_sources)
        ai_msg = await chat_crud.create_message(
            db,
            session_id=session_id,
            role="assistant",
            content=ai_content,
            model_name=llm.model_name,
            token_count=usage.get("total_tokens") or 0,
            sources=store_sources,
            disclaimer_codes=disclaimer_codes or [],
            risk_tags=risk_tags or [],
        )
        await self.service._save_prompt_snapshot(
            db=db,
            message_id=ai_msg.id,
            user_id=user_id,
            session_id=session_id,
            mode="deep_search",
            payload={
                "system_prompt": DEEP_SEARCH_ANSWER_PROMPT,
                "user_input": question,
                "chat_history": history_to_payload(chat_history),
                "deep_search": {
                    "plan": plan,
                    "queries": queries,
                    "sources": enriched_sources,
                    "context": context,
                },
                "temp_context": temp_context,
                "model_name": llm.model_name,
            },
        )
        return ai_msg

    async def _stream_deep_search(
        self,
        db,
        user_id: int,
        session_id: int,
        input_text: str,
        model: Optional[str],
        chat_history: List[BaseMessage],
        user_message_id: Optional[int] = None,
        deep_think: bool = False,
        disclaimer_codes: Optional[list[str]] = None,
        risk_tags: Optional[list[str]] = None,
    ) -> AsyncGenerator[str, None]:
        yield f"data: {json.dumps({'event': 'stage', 'stage': 'plan', 'message': '分析问题'})}\n\n"
        plan = await self._build_reasoning_plan(db, user_id, session_id, input_text, chat_history, model)
        yield f"data: {json.dumps({'event': 'stage', 'stage': 'search', 'message': '联网检索中'})}\n\n"
        queries = await self._build_search_queries(db, user_id, session_id, input_text, chat_history, model)
        sources = await self._search_web(queries)
        yield f"data: {json.dumps({'event': 'stage', 'stage': 'fetch', 'message': '抓取网页内容'})}\n\n"
        enriched_sources = await fetch_web_sources(sources, top_n=4)
        context = build_search_context(enriched_sources)
        temp_context = await self.service._get_temp_context(db, user_id, input_text)
        user_payload = (
            f"用户问题：{input_text}\n\n"
            f"【思考计划】\n{json.dumps(plan, ensure_ascii=False)}\n\n"
            f"【检索资料】\n{context or '暂无可用资料'}\n\n"
            "请不要直接输出以上计划。"
        )
        if temp_context:
            user_payload += f"\n\n【临时资料】\n{temp_context}"

        yield f"data: {json.dumps({'event': 'stage', 'stage': 'synthesize', 'message': '整理回答'})}\n\n"
        resolved = await self.service._resolve_user_llm_config(db, user_id, model)
        llm = self.service._get_llm(
            resolved["model"],
            streaming=True,
            api_key=resolved["api_key"],
            api_base_url=resolved["api_base_url"],
            temperature=0.2 if deep_think else 0.3,
        )
        messages = [SystemMessage(content=DEEP_SEARCH_ANSWER_PROMPT), HumanMessage(content=user_payload)]

        full_content = ""
        timer = UsageTimer()
        async for chunk in llm.astream(messages):
            token = getattr(chunk, "content", "")
            if not token:
                continue
            full_content += token
            yield f"data: {json.dumps({'content': token})}\n\n"

        latency_ms = timer.stop_ms()
        usage = llm_runtime_service.finalize_usage(llm=llm, messages=messages, output_text=full_content, payload={})
        await llm_runtime_service.record_success(
            db=db,
            user_id=user_id,
            event_type="deep_search_answer",
            model_name=resolved["model"],
            usage=usage,
            latency_ms=latency_ms,
            metadata={"session_id": session_id, "query_count": len(queries)},
        )

        store_sources = strip_source_content(enriched_sources)
        ai_msg = await chat_crud.create_message(
            db,
            session_id=session_id,
            role="assistant",
            content=full_content,
            model_name=resolved["model"],
            token_count=usage.get("total_tokens") or 0,
            sources=store_sources,
            disclaimer_codes=disclaimer_codes or [],
            risk_tags=risk_tags or [],
        )
        await self.service._save_prompt_snapshot(
            db=db,
            message_id=ai_msg.id,
            user_id=user_id,
            session_id=session_id,
            mode="deep_search_stream",
            payload={
                "system_prompt": DEEP_SEARCH_ANSWER_PROMPT,
                "user_input": input_text,
                "chat_history": history_to_payload(chat_history),
                "deep_search": {
                    "plan": plan,
                    "queries": queries,
                    "sources": enriched_sources,
                    "context": context,
                },
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
                "model_name": ai_msg.model_name,
                "token_count": ai_msg.token_count,
                "created_at": ai_msg.created_at.isoformat(),
                "sources": store_sources,
                "disclaimers": ai_msg.disclaimers,
                "risk_tags": ai_msg.risk_tags,
            },
            "user_message_id": user_message_id,
        }
        yield f"data: {json.dumps(payload)}\n\n"
