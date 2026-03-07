"""RAG聊天辅助模块（检索增强生成）"""

import json
from typing import AsyncGenerator, List, Optional

from langchain_core.messages import HumanMessage, SystemMessage, BaseMessage
from sqlalchemy.ext.asyncio import AsyncSession

from app.constant.prompts import RAG_SYSTEM_PROMPT
from app.crud.chat import chat_crud
from app.schemas.chat import KnowledgeChatRequest
from app.services.knowledge import kb_service
from app.services.query_rewrite import query_rewrite_service
from app.services.usage import usage_service, UsageTimer
from app.utils.chat_history import history_to_payload
from app.utils.llm_usage import estimate_usage

class ChatRagMixin:
    """RAG Mixin：提供基于知识库的问答功能（检索增强生成）"""

    async def _stream_rag_with_context(
        self,
        db: AsyncSession,
        user_id: int,
        session_id: int,
        kb_id: int,
        input_text: str,
        model: Optional[str],
        user_message_id: Optional[int] = None,
        disclaimer_codes: Optional[list[str]] = None,
        risk_tags: Optional[list[str]] = None,
        chat_history: Optional[List[BaseMessage]] = None,
    ) -> AsyncGenerator[str, None]:
        """流式RAG回答（内部方法，带已有上下文）
        
        Args:
            db: 数据库会话
            user_id: 用户ID
            session_id: 会话ID
            kb_id: 知识库ID
            input_text: 用户输入
            model: 使用的模型名称
            user_message_id: 用户消息ID
            disclaimer_codes: 免责声明代码列表
            risk_tags: 风险标签列表
            chat_history: 对话历史
            
        Yields:
            SSE格式的数据流，包含内容令牌和完成事件
        """
        rewritten_query = await query_rewrite_service.rewrite_query(input_text, user_id=user_id, kb_id=kb_id, db=db)

        context, sources = await kb_service.search_knowledge(
            kb_id=kb_id,
            query=input_text,
            top_k=4,
            rewritten_query=rewritten_query,
            user_id=user_id
        )

        rewrite_hint = ""
        if rewritten_query and rewritten_query.strip() and rewritten_query != input_text:
            rewrite_hint = f"\n【问题改写】：{rewritten_query}"

        temp_context = await self._get_temp_context(db, user_id, input_text)
        temp_hint = f"\n【临时资料】\n{temp_context}" if temp_context else ""
        system_prompt = (
            f"{RAG_SYSTEM_PROMPT}"
            f"{rewrite_hint}\n"
            f"【已知信息】：\n{context if context else '未找到相关参考资料。'}"
            f"{temp_hint}"
        )

        messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=input_text)
        ]

        resolved = await self._resolve_user_llm_config(db, user_id, model)
        llm = self._get_llm(
            resolved["model"],
            streaming=True,
            api_key=resolved["api_key"],
            api_base_url=resolved["api_base_url"],
        )
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
            event_type="kb_chat_stream",
            model_name=resolved["model"],
            prompt_tokens=usage.get("prompt_tokens"),
            completion_tokens=usage.get("completion_tokens"),
            total_tokens=usage.get("total_tokens"),
            token_missing=bool(usage.get("token_missing")),
            latency_ms=latency_ms,
            cost_usd=cost_usd,
            success=True,
            metadata={"kb_id": kb_id, "session_id": session_id},
        )

        ai_msg_db = await chat_crud.create_message(
            db,
            session_id=session_id,
            role="assistant",
            content=full_content,
            kb_id=kb_id,
            model_name=resolved["model"],
            token_count=total_tokens,
            sources=sources,
            disclaimer_codes=disclaimer_codes or [],
            risk_tags=risk_tags or [],
        )
        await self._save_prompt_snapshot(
            db=db,
            message_id=ai_msg_db.id,
            user_id=user_id,
            session_id=session_id,
            mode="rag_stream",
            payload={
                "system_prompt": system_prompt,
                "user_input": input_text,
                "chat_history": history_to_payload(chat_history or []),
                "rag": {"kb_id": kb_id, "context": context, "sources": sources, "rewrite": rewritten_query},
                "temp_context": temp_context,
                "model_name": resolved["model"],
            },
        )

        payload = {
            "event": "done",
            "message": {
                "id": ai_msg_db.id,
                "session_id": session_id,
                "role": "assistant",
                "content": ai_msg_db.content,
                "model_name": resolved["model"],
                "token_count": ai_msg_db.token_count,
                "created_at": ai_msg_db.created_at.isoformat(),
                "sources": sources,
                "disclaimers": ai_msg_db.disclaimers,
                "risk_tags": ai_msg_db.risk_tags,
            },
            "user_message_id": user_message_id,
        }
        yield f"data: {json.dumps(payload)}\n\n"

    async def handle_rag_chat(
            self,
            db: AsyncSession,
            user_id: int,
            req: KnowledgeChatRequest
    ):
        """处理知识库问答（非流式）
        
        Args:
            db: 数据库会话
            user_id: 用户ID
            req: 知识库聊天请求对象
            
        Returns:
            包含AI回复的字典
        """
        # 1) 获取或创建会话
        session_id = req.session_id
        if not session_id:
            # 创建一个新会话，标题取用户提问的前 15 个字
            session = await chat_crud.create_session(
                db,
                user_id=user_id,
                title=req.message[:15]
            )
            session_id = session.id

        # 2) 保存用户问题
        session = await chat_crud.get_session(db, session_id)
        await chat_crud.create_message(
            db,
            session_id=session_id,
            role="user",
            content=req.message,
            kb_id=req.kb_id
        )
        if session:
            await self._auto_rename_session(db, session, req.message)

        # 3) 查询改写：提升检索与问答效果
        rewritten_query = await query_rewrite_service.rewrite_query(req.message, user_id=user_id, kb_id=req.kb_id, db=db)

        # 4) 检索知识库内容（使用改写后的查询）
        context, sources = await kb_service.search_knowledge(
            kb_id=req.kb_id,
            query=req.message,
            top_k=3,
            rewritten_query=rewritten_query,
            user_id=user_id
        )

        # 5) 构建 Prompt 并调用 LLM
        rewrite_hint = ""
        if rewritten_query and rewritten_query.strip() and rewritten_query != req.message:
            rewrite_hint = f"\n【问题改写】：{rewritten_query}"

        temp_context = await self._get_temp_context(db, user_id, req.message)
        temp_hint = f"\n【临时资料】\n{temp_context}" if temp_context else ""
        system_prompt = (
            f"{RAG_SYSTEM_PROMPT}"
            f"{rewrite_hint}\n"
            f"【已知信息】：\n{context if context else '未找到相关参考资料。'}"
            f"{temp_hint}"
        )

        messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=req.message)
        ]

        # 6) 风险识别
        disclaimer_codes, risk_tags = await self._get_risk_info(
            db=db,
            user_id=user_id,
            text=req.message,
            model=req.model,
        )

        # 7) 调用大模型
        resolved = await self._resolve_user_llm_config(db, user_id, req.model)
        llm = self._get_llm(
            resolved["model"],
            api_key=resolved["api_key"],
            api_base_url=resolved["api_base_url"],
        )
        timer = UsageTimer()
        try:
            response = await llm.ainvoke(messages)
        except Exception as exc:
            latency_ms = timer.stop_ms()
            await usage_service.record_event(
                db,
                user_id=user_id,
                event_type="kb_chat",
                model_name=resolved["model"],
                prompt_tokens=None,
                completion_tokens=None,
                total_tokens=None,
                token_missing=True,
                latency_ms=latency_ms,
                cost_usd=0.0,
                success=False,
                error_message=str(exc),
                metadata={"kb_id": req.kb_id, "session_id": session_id},
            )
            raise

        latency_ms = timer.stop_ms()
        ai_content = response.content

        # 7) 提取 Token 消耗信息
        usage = usage_service.extract_usage(response)
        if usage.get("token_missing") or usage.get("total_tokens") is None:
            usage = estimate_usage(llm, messages, str(ai_content))
        elif usage.get("total_tokens") is None:
            usage["total_tokens"] = (usage.get("prompt_tokens") or 0) + (usage.get("completion_tokens") or 0)
        total_tokens = usage.get("total_tokens") or 0
        cost_usd = usage_service.compute_cost(
            resolved["model"],
            usage.get("prompt_tokens"),
            usage.get("completion_tokens"),
        )
        await usage_service.record_event(
            db,
            user_id=user_id,
            event_type="kb_chat",
            model_name=resolved["model"],
            prompt_tokens=usage.get("prompt_tokens"),
            completion_tokens=usage.get("completion_tokens"),
            total_tokens=usage.get("total_tokens"),
            token_missing=bool(usage.get("token_missing")),
            latency_ms=latency_ms,
            cost_usd=cost_usd,
            success=True,
            metadata={"kb_id": req.kb_id, "session_id": session_id},
        )

        # 8) 保存 AI 回复
        ai_msg_db = await chat_crud.create_message(
            db,
            session_id=session_id,
            role="assistant",
            content=ai_content,
            kb_id=req.kb_id,
            model_name=resolved["model"],
            token_count=total_tokens,
            sources=sources,
            disclaimer_codes=disclaimer_codes,
            risk_tags=risk_tags,
        )
        await self._save_prompt_snapshot(
            db=db,
            message_id=ai_msg_db.id,
            user_id=user_id,
            session_id=session_id,
            mode="rag",
            payload={
                "system_prompt": system_prompt,
                "user_input": req.message,
                "chat_history": [],
                "rag": {"kb_id": req.kb_id, "context": context, "sources": sources, "rewrite": rewritten_query},
                "temp_context": temp_context,
                "model_name": resolved["model"],
            },
        )

        # 9) 返回接口响应
        return {
            "id": ai_msg_db.id,
            "session_id": session_id,
            "role": "assistant",
            "content": ai_content,
            "model_name": resolved["model"],
            "token_count": total_tokens,
            "created_at": ai_msg_db.created_at,
            "sources": sources,
            "disclaimers": ai_msg_db.disclaimers,
            "risk_tags": ai_msg_db.risk_tags,
        }

    async def stream_rag_chat(
            self,
            db: AsyncSession,
            user_id: int,
            req: KnowledgeChatRequest
    ) -> AsyncGenerator[str, None]:
        """流式知识库问答
        
        Args:
            db: 数据库会话
            user_id: 用户ID
            req: 知识库聊天请求对象
            
        Yields:
            SSE格式的数据流
        """
        session_id = req.session_id
        if not session_id:
            session = await chat_crud.create_session(
                db,
                user_id=user_id,
                title=req.message[:15]
            )
            session_id = session.id

        session = await chat_crud.get_session(db, session_id)
        user_msg = await chat_crud.create_message(
            db,
            session_id=session_id,
            role="user",
            content=req.message,
            kb_id=req.kb_id
        )
        if session:
            await self._auto_rename_session(db, session, req.message)
        chat_history = await self._build_langchain_history(db, session_id, limit=10)
        disclaimer_codes, risk_tags = await self._get_risk_info(
            db=db,
            user_id=user_id,
            text=req.message,
            model=req.model,
        )
        async for payload in self._stream_rag_with_context(
            db=db,
            user_id=user_id,
            session_id=session_id,
            kb_id=req.kb_id,
            input_text=req.message,
            model=req.model,
            user_message_id=user_msg.id,
            disclaimer_codes=disclaimer_codes,
            risk_tags=risk_tags,
            chat_history=chat_history,
        ):
            yield payload
