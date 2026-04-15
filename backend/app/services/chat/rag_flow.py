"""知识库增强聊天流程：处理 RAG 同步与流式会话。"""

from __future__ import annotations

import json
from typing import AsyncGenerator, List, Optional

from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage

from app.constant.prompts import RAG_SYSTEM_PROMPT
from app.crud.chat import chat_crud
from app.schemas.chat import KnowledgeChatRequest
from app.services.knowledge import kb_service
from app.services.shared.llm_runtime import llm_runtime_service
from app.services.shared.query_rewrite import query_rewrite_service
from app.services.shared.usage import UsageTimer
from app.utils.chat_history import history_to_payload


class ChatRagFlow:
    """封装 RAG 聊天的同步与流式执行逻辑。"""

    def __init__(self, service):
        self.service = service

    async def _build_rag_runtime(
        self,
        db,
        user_id: int,
        kb_id: int,
        input_text: str,
        model: Optional[str],
        top_k: int,
    ) -> dict:
        rewritten_query = await query_rewrite_service.rewrite_query(
            input_text,
            user_id=user_id,
            kb_id=kb_id,
            db=db,
        )
        context, sources = await kb_service.search_knowledge(
            kb_id=kb_id,
            query=input_text,
            top_k=top_k,
            rewritten_query=rewritten_query,
            user_id=user_id,
        )
        rewrite_hint = ""
        if rewritten_query and rewritten_query.strip() and rewritten_query != input_text:
            rewrite_hint = f"\n【问题改写】：{rewritten_query}"

        temp_context = await self.service._get_temp_context(db, user_id, input_text)
        temp_hint = f"\n【临时资料】\n{temp_context}" if temp_context else ""
        system_prompt = (
            f"{RAG_SYSTEM_PROMPT}"
            f"{rewrite_hint}\n"
            f"【已知信息】：\n{context if context else '未找到相关参考资料。'}"
            f"{temp_hint}"
        )
        messages = [SystemMessage(content=system_prompt), HumanMessage(content=input_text)]
        resolved = await self.service._resolve_user_llm_config(db, user_id, model)
        return {
            "rewritten_query": rewritten_query,
            "context": context,
            "sources": sources,
            "temp_context": temp_context,
            "system_prompt": system_prompt,
            "messages": messages,
            "resolved": resolved,
        }

    async def _stream_rag_with_context(
        self,
        db,
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
        runtime = await self._build_rag_runtime(db, user_id, kb_id, input_text, model, top_k=4)
        llm = self.service._get_llm(
            runtime["resolved"]["model"],
            streaming=True,
            api_key=runtime["resolved"]["api_key"],
            api_base_url=runtime["resolved"]["api_base_url"],
        )

        full_content = ""
        timer = UsageTimer()
        async for chunk in llm.astream(runtime["messages"]):
            token = getattr(chunk, "content", "")
            if not token:
                continue
            full_content += token
            yield f"data: {json.dumps({'content': token})}\n\n"

        latency_ms = timer.stop_ms()
        usage = llm_runtime_service.finalize_usage(
            llm=llm,
            messages=runtime["messages"],
            output_text=full_content,
            payload={},
        )
        await llm_runtime_service.record_success(
            db=db,
            user_id=user_id,
            event_type="kb_chat_stream",
            model_name=runtime["resolved"]["model"],
            usage=usage,
            latency_ms=latency_ms,
            metadata={"kb_id": kb_id, "session_id": session_id},
        )

        ai_msg_db = await chat_crud.create_message(
            db,
            session_id=session_id,
            role="assistant",
            content=full_content,
            kb_id=kb_id,
            model_name=runtime["resolved"]["model"],
            token_count=usage.get("total_tokens") or 0,
            sources=runtime["sources"],
            disclaimer_codes=disclaimer_codes or [],
            risk_tags=risk_tags or [],
        )
        await self.service._save_prompt_snapshot(
            db=db,
            message_id=ai_msg_db.id,
            user_id=user_id,
            session_id=session_id,
            mode="rag_stream",
            payload={
                "system_prompt": runtime["system_prompt"],
                "user_input": input_text,
                "chat_history": history_to_payload(chat_history or []),
                "rag": {
                    "kb_id": kb_id,
                    "context": runtime["context"],
                    "sources": runtime["sources"],
                    "rewrite": runtime["rewritten_query"],
                },
                "temp_context": runtime["temp_context"],
                "model_name": runtime["resolved"]["model"],
            },
        )

        payload = {
            "event": "done",
            "message": {
                "id": ai_msg_db.id,
                "session_id": session_id,
                "role": "assistant",
                "content": ai_msg_db.content,
                "model_name": runtime["resolved"]["model"],
                "token_count": ai_msg_db.token_count,
                "created_at": ai_msg_db.created_at.isoformat(),
                "sources": runtime["sources"],
                "disclaimers": ai_msg_db.disclaimers,
                "risk_tags": ai_msg_db.risk_tags,
            },
            "user_message_id": user_message_id,
        }
        yield f"data: {json.dumps(payload)}\n\n"

    async def handle_rag_chat(self, db, user_id: int, req: KnowledgeChatRequest):
        session_id = req.session_id
        if not session_id:
            session = await chat_crud.create_session(db, user_id=user_id, title=req.message[:15])
            session_id = session.id

        session = await chat_crud.get_session(db, session_id)
        await chat_crud.create_message(db, session_id=session_id, role="user", content=req.message, kb_id=req.kb_id)
        if session:
            await self.service._auto_rename_session(db, session, req.message)

        runtime = await self._build_rag_runtime(db, user_id, req.kb_id, req.message, req.model, top_k=3)
        disclaimer_codes, risk_tags = await self.service._get_risk_info(
            db=db,
            user_id=user_id,
            text=req.message,
            model=req.model,
            resolved=runtime["resolved"],
        )

        llm = self.service._get_llm(
            runtime["resolved"]["model"],
            api_key=runtime["resolved"]["api_key"],
            api_base_url=runtime["resolved"]["api_base_url"],
        )
        timer = UsageTimer()
        try:
            response = await llm.ainvoke(runtime["messages"])
        except Exception as exc:
            latency_ms = timer.stop_ms()
            await llm_runtime_service.record_failure(
                db=db,
                user_id=user_id,
                event_type="kb_chat",
                model_name=runtime["resolved"]["model"],
                error=exc,
                latency_ms=latency_ms,
                metadata={"kb_id": req.kb_id, "session_id": session_id},
            )
            raise

        latency_ms = timer.stop_ms()
        ai_content = getattr(response, "content", "") or ""
        usage = llm_runtime_service.finalize_usage(
            llm=llm,
            messages=runtime["messages"],
            output_text=str(ai_content),
            payload=response,
        )
        await llm_runtime_service.record_success(
            db=db,
            user_id=user_id,
            event_type="kb_chat",
            model_name=runtime["resolved"]["model"],
            usage=usage,
            latency_ms=latency_ms,
            metadata={"kb_id": req.kb_id, "session_id": session_id},
        )

        ai_msg_db = await chat_crud.create_message(
            db,
            session_id=session_id,
            role="assistant",
            content=ai_content,
            kb_id=req.kb_id,
            model_name=runtime["resolved"]["model"],
            token_count=usage.get("total_tokens") or 0,
            sources=runtime["sources"],
            disclaimer_codes=disclaimer_codes,
            risk_tags=risk_tags,
        )
        await self.service._save_prompt_snapshot(
            db=db,
            message_id=ai_msg_db.id,
            user_id=user_id,
            session_id=session_id,
            mode="rag",
            payload={
                "system_prompt": runtime["system_prompt"],
                "user_input": req.message,
                "chat_history": [],
                "rag": {
                    "kb_id": req.kb_id,
                    "context": runtime["context"],
                    "sources": runtime["sources"],
                    "rewrite": runtime["rewritten_query"],
                },
                "temp_context": runtime["temp_context"],
                "model_name": runtime["resolved"]["model"],
            },
        )
        return {
            "id": ai_msg_db.id,
            "session_id": session_id,
            "role": "assistant",
            "content": ai_content,
            "model_name": runtime["resolved"]["model"],
            "token_count": usage.get("total_tokens") or 0,
            "created_at": ai_msg_db.created_at,
            "sources": runtime["sources"],
            "disclaimers": ai_msg_db.disclaimers,
            "risk_tags": ai_msg_db.risk_tags,
        }

    async def stream_rag_chat(self, db, user_id: int, req: KnowledgeChatRequest) -> AsyncGenerator[str, None]:
        session_id = req.session_id
        if not session_id:
            session = await chat_crud.create_session(db, user_id=user_id, title=req.message[:15])
            session_id = session.id

        session = await chat_crud.get_session(db, session_id)
        user_msg = await chat_crud.create_message(
            db,
            session_id=session_id,
            role="user",
            content=req.message,
            kb_id=req.kb_id,
        )
        if session:
            await self.service._auto_rename_session(db, session, req.message)
        chat_history = await self.service._build_langchain_history(db, session_id, limit=10)
        disclaimer_codes, risk_tags = await self.service._get_risk_info(
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
