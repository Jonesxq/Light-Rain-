"""聊天领域门面服务：统一编排会话、工具、推理与 RAG 能力。"""

from __future__ import annotations

from typing import AsyncGenerator, Optional

from langchain_core.messages import HumanMessage, SystemMessage

from app.constant.prompts import SUGGESTION_SYSTEM_PROMPT
from app.core.config.settings import settings
from app.core.logger import logger_manager
from app.crud.chat import chat_crud
from app.crud.llm_settings import llm_settings_crud
from app.models.chat import ChatMessage, ChatRole
from app.schemas.chat import ChatRequest, KnowledgeChatRequest
from app.services.chat.dispatch import ChatDispatch
from app.services.chat.rag_flow import ChatRagFlow
from app.services.chat.reasoning_flow import ChatReasoningFlow
from app.services.chat.session_support import ChatSessionSupport
from app.services.chat.tool_flow import ChatToolFlow
from app.services.shared.llm_runtime import llm_runtime_service
from app.services.shared.usage import UsageTimer
from app.tools.text_to_image import text_to_image
from app.utils.chat_meme import build_meme_caption
from app.utils.chat_suggestions import parse_suggestions
from app.utils.crypto import decrypt_text
from app.utils.llm_factory import build_chat_llm

logger = logger_manager.get_logger(__name__)


class ChatService:
    """聊天包级门面：对外提供统一接口并委托给分域组件。"""

    def __init__(self):
        self._session_support = ChatSessionSupport(self)
        self._reasoning_flow = ChatReasoningFlow(self)
        self._tool_flow = ChatToolFlow(self)
        self._rag_flow = ChatRagFlow(self)
        self._dispatch = ChatDispatch(self)
        self._ops = (
            self._session_support,
            self._reasoning_flow,
            self._tool_flow,
            self._rag_flow,
            self._dispatch,
        )

    def __getattr__(self, name: str):
        for component in self._ops:
            if hasattr(component, name):
                return getattr(component, name)
        raise AttributeError(f"{type(self).__name__!s} has no attribute {name}")

    def _get_llm(
        self,
        model_name: Optional[str] = None,
        streaming: bool = False,
        api_key: Optional[str] = None,
        api_base_url: Optional[str] = None,
        temperature: Optional[float] = None,
    ):
        return build_chat_llm(
            model=model_name,
            api_key=api_key,
            api_base_url=api_base_url,
            temperature=0.3 if temperature is None else temperature,
            streaming=streaming,
        )

    async def _resolve_user_llm_config(self, db, user_id: int, request_model: Optional[str]) -> dict:
        model_override = (request_model or "").strip() or None

        settings_row = await llm_settings_crud.get_by_user_id(db, user_id)
        if not settings_row or not settings_row.enabled:
            return {
                "model": model_override or settings.llm.DEFAULT_MODEL,
                "api_key": settings.llm.QWEN_API_KEY,
                "api_base_url": settings.llm.QWEN_BASE_URL,
            }

        if not settings_row.api_key_encrypted:
            logger.warning("User LLM settings enabled but API key missing, fallback to system config.")
            return {
                "model": model_override or settings.llm.DEFAULT_MODEL,
                "api_key": settings.llm.QWEN_API_KEY,
                "api_base_url": settings.llm.QWEN_BASE_URL,
            }

        try:
            api_key = decrypt_text(settings_row.api_key_encrypted)
        except Exception as exc:
            logger.error(f"User LLM key decrypt failed: {exc}")
            raise ValueError("用户模型配置解密失败")

        return {
            "model": model_override or settings_row.model or settings.llm.DEFAULT_MODEL,
            "api_key": api_key,
            "api_base_url": settings_row.api_base_url or settings.llm.QWEN_BASE_URL,
        }

    async def process_chat(self, db, user_id: int, session_id: int, chat_request: ChatRequest):
        return await self._dispatch.process_chat(db, user_id, session_id, chat_request)

    async def stream_chat(self, db, user_id: int, session_id: int, chat_request: ChatRequest) -> AsyncGenerator[str, None]:
        async for payload in self._dispatch.stream_chat(db, user_id, session_id, chat_request):
            yield payload

    async def stream_resend(
        self,
        db,
        user_id: int,
        message_id: int,
        new_message: str,
        deep_search: bool = False,
        deep_think: bool = False,
    ) -> AsyncGenerator[str, None]:
        async for payload in self._dispatch.stream_resend(db, user_id, message_id, new_message, deep_search, deep_think):
            yield payload

    async def stream_regenerate(
        self,
        db,
        user_id: int,
        message_id: int,
        deep_search: bool = False,
        deep_think: bool = False,
    ) -> AsyncGenerator[str, None]:
        async for payload in self._dispatch.stream_regenerate(db, user_id, message_id, deep_search, deep_think):
            yield payload

    async def handle_rag_chat(self, db, user_id: int, req: KnowledgeChatRequest):
        return await self._rag_flow.handle_rag_chat(db, user_id, req)

    async def stream_rag_chat(self, db, user_id: int, req: KnowledgeChatRequest) -> AsyncGenerator[str, None]:
        async for payload in self._rag_flow.stream_rag_chat(db, user_id, req):
            yield payload

    async def generate_meme(self, db, user_id: int, message_id: int) -> ChatMessage:
        message = await chat_crud.get_message(db, message_id)
        if not message:
            raise ValueError("Message not found")
        session = await chat_crud.get_session(db, message.session_id)
        if not session or session.user_id != user_id:
            raise ValueError("Message not found")
        if message.role != ChatRole.ASSISTANT:
            raise ValueError("Only assistant messages are supported")

        caption = build_meme_caption(message.content or "")
        prompt = f"网络表情包风格，夸张搞笑，简洁背景，高清，白色粗体描边中文文字：{caption}"
        try:
            image_url = text_to_image.invoke({"prompt": prompt})
        except Exception:
            image_url = text_to_image.run(prompt)

        if not image_url or str(image_url).startswith("文生图失败"):
            raise RuntimeError(str(image_url) or "文生图失败")
        if isinstance(image_url, str) and "\n" in image_url:
            image_url = image_url.splitlines()[0].strip()

        content = f"![meme]({image_url})"
        ai_msg = await chat_crud.create_message(
            db,
            session_id=session.id,
            role="assistant",
            content=content,
            model_name=getattr(settings.llm, "TEXT_TO_IMAGE_MODEL", None),
            token_count=0,
        )
        await chat_crud.update_session_time(db, session.id)
        return ai_msg

    async def suggest_followups(
        self,
        db,
        user_id: int,
        session_id: int,
        limit: int = 3,
        model: Optional[str] = None,
    ) -> list[str]:
        limit = max(1, min(int(limit or 3), 6))
        messages = await chat_crud.get_session_messages(db, session_id)
        if not messages:
            return []

        filtered = [message for message in messages if message.role in (ChatRole.USER, ChatRole.ASSISTANT)]
        if len(filtered) < 2:
            return []

        context_lines = []
        for message in filtered[-12:]:
            content = (message.content or "").strip()
            if not content:
                continue
            if len(content) > 200:
                content = content[:200] + "..."
            role_label = "用户" if message.role == ChatRole.USER else "助手"
            context_lines.append(f"{role_label}: {content}")

        if len(context_lines) < 2:
            return []

        resolved = await self._resolve_user_llm_config(db, user_id, model)
        llm = build_chat_llm(
            model=resolved["model"],
            api_key=resolved["api_key"],
            api_base_url=resolved["api_base_url"],
            temperature=0.7,
            streaming=False,
        )
        llm_messages = [
            SystemMessage(content=SUGGESTION_SYSTEM_PROMPT),
            HumanMessage(content="\n".join(context_lines)),
        ]
        timer = UsageTimer()
        try:
            response = await llm.ainvoke(llm_messages)
        except Exception as exc:
            await llm_runtime_service.record_failure(
                db=db,
                user_id=user_id,
                event_type="chat_suggestions",
                model_name=None,
                error=exc,
                latency_ms=timer.stop_ms(),
                metadata={"session_id": session_id},
            )
            logger.warning(f"Suggestion generation failed: {exc}")
            return []

        latency_ms = timer.stop_ms()
        usage = llm_runtime_service.finalize_usage(
            llm=llm,
            messages=llm_messages,
            output_text=getattr(response, "content", "") or "",
            payload=response,
        )
        await llm_runtime_service.record_success(
            db=db,
            user_id=user_id,
            event_type="chat_suggestions",
            model_name=llm.model_name,
            usage=usage,
            latency_ms=latency_ms,
            metadata={"session_id": session_id},
        )
        suggestions = parse_suggestions(getattr(response, "content", "") or "")
        return suggestions[:limit] if suggestions else []
