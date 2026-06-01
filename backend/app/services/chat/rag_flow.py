"""知识库增强聊天流程：处理 RAG 同步与流式会话。"""

from __future__ import annotations

import json
from typing import AsyncGenerator, List, Optional

from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage

from app.constant.prompts import RAG_SYSTEM_PROMPT
from app.core.config import settings
from app.core.logger import logger_manager
from app.crud.chat import chat_crud
from app.crud.wiki import wiki_crud
from app.schemas.chat import KnowledgeChatRequest
from app.services.knowledge import kb_service
from app.services.shared.llm_runtime import llm_runtime_service
from app.services.shared.query_rewrite import query_rewrite_service
from app.services.shared.usage import UsageTimer
from app.services.wiki import wiki_service
from app.services.wiki.markdown import extract_frontmatter
from app.services.wiki.types import PAGE_FAQ, WikiSearchHit
from app.utils.chat_history import history_to_payload

logger = logger_manager.get_logger(__name__)


class ChatRagFlow:
    """封装 RAG 聊天的同步与流式执行逻辑。"""

    def __init__(self, service):
        self.service = service

    def _wiki_hit_is_confident(self, hits: list[WikiSearchHit]) -> bool:
        if not hits:
            return False
        threshold = settings.wiki.WIKI_ANSWER_CONFIDENCE_THRESHOLD
        return hits[0].score >= threshold

    def _serialize_wiki_hits(self, hits: list[WikiSearchHit]) -> list[dict]:
        return [
            {
                "page_id": hit.page_id,
                "path": hit.path,
                "title": hit.title,
                "page_type": hit.page_type,
                "score": hit.score,
                "snippet": hit.snippet,
            }
            for hit in hits
        ]

    def _wiki_sources_from_hits(self, hits: list[WikiSearchHit]) -> list[dict]:
        return [
            {
                "source_type": "wiki",
                "title": hit.title,
                "snippet": hit.snippet,
                "file_name": hit.path,
                "file_type": ".md",
                "md_headings": hit.title,
                "chunk_id": hit.page_id,
            }
            for hit in hits
        ]

    def _wiki_context_from_hits(
        self,
        *,
        kb_id: int,
        hits: list[WikiSearchHit],
    ) -> str:
        remaining_chars = settings.wiki.WIKI_MAX_PAGE_CHARS
        sections: list[str] = []

        for hit in hits:
            if remaining_chars <= 0:
                break
            try:
                markdown = wiki_service.storage.read_page(kb_id, hit.path)
            except (FileNotFoundError, OSError, UnicodeError, ValueError):
                continue

            _frontmatter, body = extract_frontmatter(markdown)
            page_text = body.strip() or markdown.strip()
            if not page_text:
                continue

            excerpt = page_text[:remaining_chars]
            remaining_chars -= len(excerpt)
            sections.append(
                "\n".join(
                    [
                        f"【Wiki页面】：{hit.title}",
                        f"【路径】：{hit.path}",
                        excerpt,
                    ]
                )
            )

        return "\n\n---\n\n".join(sections)

    async def _build_wiki_runtime(
        self,
        db,
        user_id: int,
        kb_id: int,
        input_text: str,
        model: Optional[str],
    ) -> Optional[dict]:
        if not settings.wiki.WIKI_RAG_ENABLED:
            return None

        try:
            hits = await wiki_service.search_pages(
                db,
                kb_id=kb_id,
                query=input_text,
                top_k=settings.wiki.WIKI_RETRIEVER_TOP_K,
            )
        except Exception as exc:
            logger.warning(
                f"Wiki first retrieval failed, falling back to raw RAG: {exc}"
            )
            return None
        if not self._wiki_hit_is_confident(hits):
            return None

        context = self._wiki_context_from_hits(kb_id=kb_id, hits=hits)
        if not context:
            return None

        temp_context = await self.service._get_temp_context(db, user_id, input_text)
        temp_hint = f"\n【临时资料】\n{temp_context}" if temp_context else ""
        system_prompt = (
            f"{RAG_SYSTEM_PROMPT}\n"
            "【检索策略】：优先使用已编译 Wiki 页面回答。"
            "请只基于 Wiki 页面和临时资料回答；"
            "如果没有明确依据，请说明知识库中没有找到明确依据。\n"
            f"【已知信息】：\n{context}"
            f"{temp_hint}"
        )
        resolved = await self.service._resolve_user_llm_config(db, user_id, model)
        return {
            "strategy": "wiki_first",
            "rewritten_query": None,
            "context": context,
            "sources": self._wiki_sources_from_hits(hits),
            "temp_context": temp_context,
            "system_prompt": system_prompt,
            "messages": [
                SystemMessage(content=system_prompt),
                HumanMessage(content=input_text),
            ],
            "resolved": resolved,
            "wiki_hits": self._serialize_wiki_hits(hits),
        }

    async def _build_knowledge_runtime(
        self,
        db,
        user_id: int,
        kb_id: int,
        input_text: str,
        model: Optional[str],
        top_k: int,
    ) -> dict:
        wiki_runtime = await self._build_wiki_runtime(
            db,
            user_id=user_id,
            kb_id=kb_id,
            input_text=input_text,
            model=model,
        )
        if wiki_runtime is not None:
            return wiki_runtime

        runtime = await self._build_rag_runtime(
            db,
            user_id,
            kb_id,
            input_text,
            model,
            top_k=top_k,
        )
        runtime["strategy"] = "rag_fallback"
        runtime["wiki_hits"] = []
        return runtime

    def _snapshot_mode(self, runtime: dict, *, streaming: bool) -> str:
        if runtime.get("strategy") == "wiki_first":
            return "wiki_first_stream" if streaming else "wiki_first"
        return "rag_fallback_stream" if streaming else "rag_fallback"

    def _snapshot_payload(
        self,
        *,
        runtime: dict,
        kb_id: int,
        input_text: str,
        chat_history: list[BaseMessage],
    ) -> dict:
        return {
            "system_prompt": runtime["system_prompt"],
            "user_input": input_text,
            "chat_history": history_to_payload(chat_history),
            "rag": {
                "kb_id": kb_id,
                "context": runtime["context"],
                "sources": runtime["sources"],
                "rewrite": runtime["rewritten_query"],
            },
            "wiki": {
                "strategy": runtime.get("strategy", "rag_fallback"),
                "hits": runtime.get("wiki_hits", []),
            },
            "temp_context": runtime["temp_context"],
            "model_name": runtime["resolved"]["model"],
        }

    async def _maybe_create_wiki_patch(
        self,
        db,
        *,
        kb_id: int,
        question: str,
        answer: str,
        sources: list[dict],
        assistant_message_id: int,
    ) -> None:
        if settings.wiki.WIKI_WRITEBACK_MODE == "disabled":
            return
        if not answer.strip() or not sources:
            return

        patch_markdown = "\n".join(
            [
                f"## {question.strip()[:80]}",
                "",
                f"**问题：** {question.strip()}",
                "",
                "**回答：**",
                "",
                answer.strip(),
                "",
                "<!-- 来源：RAG 兜底回答，待人工审核后写入 Wiki -->",
            ]
        )
        try:
            await wiki_crud.create_patch(
                db,
                kb_id=kb_id,
                target_path=PAGE_FAQ,
                operation="append",
                status="pending",
                question=question,
                answer=answer,
                patch_markdown=patch_markdown,
                rationale="RAG 兜底生成了可复用答案，建议人工审核后写入 Wiki。",
                confidence=settings.wiki.WIKI_PATCH_CONFIDENCE_THRESHOLD,
                provenance={
                    "strategy": "rag_fallback",
                    "sources": sources,
                },
                created_by_message_id=assistant_message_id,
            )
        except Exception as exc:
            logger.warning(
                "Wiki writeback patch creation failed for message "
                f"{assistant_message_id}: {exc}"
            )

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
        if (
            rewritten_query
            and rewritten_query.strip()
            and rewritten_query != input_text
        ):
            rewrite_hint = f"\n【问题改写】：{rewritten_query}"

        temp_context = await self.service._get_temp_context(db, user_id, input_text)
        temp_hint = f"\n【临时资料】\n{temp_context}" if temp_context else ""
        system_prompt = (
            f"{RAG_SYSTEM_PROMPT}"
            f"{rewrite_hint}\n"
            f"【已知信息】：\n{context if context else '未找到相关参考资料。'}"
            f"{temp_hint}"
        )
        messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=input_text),
        ]
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
        runtime = await self._build_knowledge_runtime(
            db,
            user_id,
            kb_id,
            input_text,
            model,
            top_k=4,
        )
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
            mode=self._snapshot_mode(runtime, streaming=True),
            payload=self._snapshot_payload(
                runtime=runtime,
                kb_id=kb_id,
                input_text=input_text,
                chat_history=chat_history or [],
            ),
        )
        if runtime.get("strategy") == "rag_fallback":
            await self._maybe_create_wiki_patch(
                db,
                kb_id=kb_id,
                question=input_text,
                answer=full_content,
                sources=runtime["sources"],
                assistant_message_id=ai_msg_db.id,
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
            session = await chat_crud.create_session(
                db, user_id=user_id, title=req.message[:15]
            )
            session_id = session.id

        session = await chat_crud.get_session(db, session_id)
        await chat_crud.create_message(
            db, session_id=session_id, role="user", content=req.message, kb_id=req.kb_id
        )
        if session:
            await self.service._auto_rename_session(db, session, req.message)

        runtime = await self._build_knowledge_runtime(
            db,
            user_id,
            req.kb_id,
            req.message,
            req.model,
            top_k=3,
        )
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
            mode=self._snapshot_mode(runtime, streaming=False),
            payload=self._snapshot_payload(
                runtime=runtime,
                kb_id=req.kb_id,
                input_text=req.message,
                chat_history=[],
            ),
        )
        if runtime.get("strategy") == "rag_fallback":
            await self._maybe_create_wiki_patch(
                db,
                kb_id=req.kb_id,
                question=req.message,
                answer=ai_content,
                sources=runtime["sources"],
                assistant_message_id=ai_msg_db.id,
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

    async def stream_rag_chat(
        self, db, user_id: int, req: KnowledgeChatRequest
    ) -> AsyncGenerator[str, None]:
        session_id = req.session_id
        if not session_id:
            session = await chat_crud.create_session(
                db, user_id=user_id, title=req.message[:15]
            )
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
        chat_history = await self.service._build_langchain_history(
            db, session_id, limit=10
        )
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
