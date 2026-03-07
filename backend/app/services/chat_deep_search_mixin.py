"""联网搜索（深度搜索）辅助模块"""

import asyncio
import json
from typing import AsyncGenerator, List, Optional

from langchain_community.utilities import GoogleSerperAPIWrapper
from langchain_core.messages import HumanMessage, SystemMessage, BaseMessage
from sqlalchemy.ext.asyncio import AsyncSession

from app.constant.prompts import DEEP_SEARCH_QUERY_PROMPT, DEEP_SEARCH_ANSWER_PROMPT
from app.core.config.settings import settings
from app.core.logger import logger_manager
from app.crud.chat import chat_crud
from app.models.chat import ChatMessage
from app.services.usage import usage_service, UsageTimer
from app.utils.chat_history import history_to_payload, history_to_text
from app.utils.chat_web import build_search_context, fetch_web_sources, strip_source_content
from app.utils.json_utils import parse_json_list
from app.utils.llm_usage import estimate_usage

logger = logger_manager.get_logger(__name__)


class ChatDeepSearchMixin:
    """深度搜索Mixin：提供联网搜索能力，包括搜索查询生成、网页搜索、搜索结果整合回答"""

    async def _build_search_queries(
        self,
        db: AsyncSession,
        user_id: int,
        session_id: int,
        question: str,
        chat_history: List[BaseMessage],
        model: Optional[str],
    ) -> List[str]:
        """为深度搜索生成优化的搜索查询
        
        Args:
            db: 数据库会话
            user_id: 用户ID
            session_id: 会话ID
            question: 用户问题
            chat_history: 对话历史
            model: 使用的模型名称
            
        Returns:
            搜索查询列表（最多4个）
        """
        base_question = (question or "").strip()
        if not base_question:
            return []
        history_text = history_to_text(chat_history)
        user_content = f"用户问题：{base_question}"
        if history_text:
            user_content += f"\n\n对话上下文：\n{history_text}"

        resolved = await self._resolve_user_llm_config(db, user_id, model)
        llm = self._get_llm(
            resolved["model"],
            api_key=resolved["api_key"],
            api_base_url=resolved["api_base_url"],
        )
        messages = [
            SystemMessage(content=DEEP_SEARCH_QUERY_PROMPT),
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
            queries = parse_json_list(getattr(response, "content", "") or "")
            if not queries:
                queries = [base_question]
            queries = queries[:4]
            await usage_service.record_event(
                db,
                user_id=user_id,
                event_type="deep_search_query",
                model_name=llm.model_name,
                prompt_tokens=usage.get("prompt_tokens"),
                completion_tokens=usage.get("completion_tokens"),
                total_tokens=usage.get("total_tokens"),
                token_missing=bool(usage.get("token_missing")),
                latency_ms=latency_ms,
                cost_usd=cost_usd,
                success=True,
                metadata={"session_id": session_id, "query_count": len(queries)},
            )
            return queries
        except Exception as exc:
            try:
                latency_ms = timer.stop_ms()
            except Exception:
                latency_ms = None
            try:
                await usage_service.record_event(
                    db,
                    user_id=user_id,
                    event_type="deep_search_query",
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
            logger.warning(f"深度搜索查询生成失败: {exc}")
            return [base_question]

    async def _search_web(self, queries: List[str], max_results: int = 8) -> List[dict]:
        """使用Serper API搜索网页并返回结构化来源
        
        Args:
            queries: 搜索查询列表
            max_results: 最大返回结果数
            
        Returns:
            结构化搜索来源列表，包含标题、URL、摘要等信息
            
        Raises:
            ValueError: 当SERPER_API_KEY未配置时
        """
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
                if not url:
                    continue
                if url in seen:
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

    async def _deep_search_answer(
        self,
        db: AsyncSession,
        user_id: int,
        session_id: int,
        question: str,
        chat_history: List[BaseMessage],
        model: Optional[str],
        deep_think: bool = False,
        disclaimer_codes: Optional[list[str]] = None,
        risk_tags: Optional[list[str]] = None,
    ) -> ChatMessage:
        """非流式深度搜索回答：构建思考计划、搜索网络、整合资料并生成回答
        
        Args:
            db: 数据库会话
            user_id: 用户ID
            session_id: 会话ID
            question: 用户问题
            chat_history: 对话历史
            model: 使用的模型名称
            deep_think: 是否启用深度思考模式
            disclaimer_codes: 免责声明代码列表
            risk_tags: 风险标签列表
            
        Returns:
            创建的AI聊天消息对象
        """
        plan = await self._build_reasoning_plan(db, user_id, session_id, question, chat_history, model)
        try:
            plan_text = json.dumps(plan, ensure_ascii=False)
        except Exception:
            plan_text = str(plan)

        queries = await self._build_search_queries(db, user_id, session_id, question, chat_history, model)
        sources = await self._search_web(queries)
        enriched_sources = await fetch_web_sources(sources, top_n=4)
        context = build_search_context(enriched_sources)
        temp_context = await self._get_temp_context(db, user_id, question)
        user_payload = (
            f"用户问题：{question}\n\n"
            f"【思考计划】\n{plan_text}\n\n"
            f"【检索资料】\n{context or '暂无可用资料'}\n\n"
            "请不要直接输出以上计划。"
        )
        if temp_context:
            user_payload += f"\n\n【临时资料】\n{temp_context}"

        resolved = await self._resolve_user_llm_config(db, user_id, model)
        llm = self._get_llm(
            resolved["model"],
            api_key=resolved["api_key"],
            api_base_url=resolved["api_base_url"],
            temperature=0.2 if deep_think else 0.3,
        )
        system_prompt = DEEP_SEARCH_ANSWER_PROMPT
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
            event_type="deep_search_answer",
            model_name=llm.model_name,
            prompt_tokens=usage.get("prompt_tokens"),
            completion_tokens=usage.get("completion_tokens"),
            total_tokens=usage.get("total_tokens"),
            token_missing=bool(usage.get("token_missing")),
            latency_ms=latency_ms,
            cost_usd=cost_usd,
            success=True,
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
        await self._save_prompt_snapshot(
            db=db,
            message_id=ai_msg.id,
            user_id=user_id,
            session_id=session_id,
            mode="deep_search",
            payload={
                "system_prompt": system_prompt,
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
        db: AsyncSession,
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
        """流式深度搜索回答：实时展示搜索进度并流式输出回答
        
        Args:
            db: 数据库会话
            user_id: 用户ID
            session_id: 会话ID
            input_text: 用户输入
            model: 使用的模型名称
            chat_history: 对话历史
            user_message_id: 用户消息ID
            deep_think: 是否启用深度思考模式
            disclaimer_codes: 免责声明代码列表
            risk_tags: 风险标签列表
            
        Yields:
            SSE格式的数据流，包含阶段进度、内容令牌和完成事件
        """
        yield f"data: {json.dumps({'event': 'stage', 'stage': 'plan', 'message': '分析问题'})}\n\n"
        plan = await self._build_reasoning_plan(db, user_id, session_id, input_text, chat_history, model)
        try:
            plan_text = json.dumps(plan, ensure_ascii=False)
        except Exception:
            plan_text = str(plan)

        yield f"data: {json.dumps({'event': 'stage', 'stage': 'search', 'message': '联网检索中'})}\n\n"
        queries = await self._build_search_queries(db, user_id, session_id, input_text, chat_history, model)
        sources = await self._search_web(queries)

        yield f"data: {json.dumps({'event': 'stage', 'stage': 'fetch', 'message': '抓取网页内容'})}\n\n"
        enriched_sources = await fetch_web_sources(sources, top_n=4)
        context = build_search_context(enriched_sources)
        temp_context = await self._get_temp_context(db, user_id, input_text)
        user_payload = (
            f"用户问题：{input_text}\n\n"
            f"【思考计划】\n{plan_text}\n\n"
            f"【检索资料】\n{context or '暂无可用资料'}\n\n"
            "请不要直接输出以上计划。"
        )
        if temp_context:
            user_payload += f"\n\n【临时资料】\n{temp_context}"

        yield f"data: {json.dumps({'event': 'stage', 'stage': 'synthesize', 'message': '整理回答'})}\n\n"
        resolved = await self._resolve_user_llm_config(db, user_id, model)
        llm = self._get_llm(
            resolved["model"],
            streaming=True,
            api_key=resolved["api_key"],
            api_base_url=resolved["api_base_url"],
            temperature=0.2 if deep_think else 0.3,
        )
        system_prompt = DEEP_SEARCH_ANSWER_PROMPT
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
            event_type="deep_search_answer",
            model_name=resolved["model"],
            prompt_tokens=usage.get("prompt_tokens"),
            completion_tokens=usage.get("completion_tokens"),
            total_tokens=usage.get("total_tokens"),
            token_missing=bool(usage.get("token_missing")),
            latency_ms=latency_ms,
            cost_usd=cost_usd,
            success=True,
            metadata={"session_id": session_id, "query_count": len(queries)},
        )

        store_sources = strip_source_content(enriched_sources)
        ai_msg = await chat_crud.create_message(
            db,
            session_id=session_id,
            role="assistant",
            content=full_content,
            model_name=resolved["model"],
            token_count=total_tokens,
            sources=store_sources,
            disclaimer_codes=disclaimer_codes or [],
            risk_tags=risk_tags or [],
        )
        await self._save_prompt_snapshot(
            db=db,
            message_id=ai_msg.id,
            user_id=user_id,
            session_id=session_id,
            mode="deep_search_stream",
            payload={
                "system_prompt": system_prompt,
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
