"""Session and context helpers for chat services."""

from __future__ import annotations

from typing import List, Optional

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logger import logger_manager
from app.crud.chat import chat_crud
from app.crud.chat_prompt_snapshot import chat_prompt_snapshot_crud
from app.models.chat import ChatMessage, ChatRole, ChatSession
from app.services.chat.attachments import temp_context_service
from app.services.shared.safety import safety_service

logger = logger_manager.get_logger(__name__)


class ChatSessionSupport:
    """Shared chat-session helpers used by multiple chat flows."""

    def __init__(self, service):
        self.service = service

    async def _auto_rename_session(self, db: AsyncSession, session: ChatSession, user_msg: str):
        if session.title in {"New Chat", "新对话"}:
            session.title = user_msg[:15]
            db.add(session)
            await db.commit()

    async def _build_langchain_history(self, db: AsyncSession, session_id: int, limit: int = 10) -> List[BaseMessage]:
        db_messages = await chat_crud.get_session_messages(db, session_id)
        if db_messages and db_messages[-1].role == ChatRole.USER:
            db_messages = db_messages[:-1]

        langchain_msgs: List[BaseMessage] = []
        for msg in db_messages[-limit:]:
            if msg.role == ChatRole.USER:
                langchain_msgs.append(HumanMessage(content=msg.content))
            elif msg.role == ChatRole.ASSISTANT:
                langchain_msgs.append(AIMessage(content=msg.content))
            elif msg.role == ChatRole.SYSTEM:
                langchain_msgs.append(SystemMessage(content=msg.content))
        return langchain_msgs

    async def _get_temp_context(self, db: AsyncSession, user_id: int, query: str) -> str:
        try:
            return await temp_context_service.get_context_for_user(db, user_id, query)
        except Exception:
            return ""

    async def _get_message_and_session_for_user(
        self,
        db: AsyncSession,
        user_id: int,
        message_id: int,
    ) -> tuple[ChatMessage, ChatSession]:
        message = await chat_crud.get_message(db, message_id)
        if not message:
            raise ValueError("Message not found")
        session = await chat_crud.get_session(db, message.session_id)
        if not session or session.user_id != user_id:
            raise ValueError("Message not found")
        return message, session

    async def _get_risk_info(
        self,
        db: AsyncSession,
        user_id: int,
        text: str,
        model: Optional[str],
        resolved: Optional[dict] = None,
    ) -> tuple[list[str], list[str]]:
        if not text:
            return [], []
        try:
            if resolved is None:
                resolved = await self.service._resolve_user_llm_config(db, user_id, model)
            labels = await safety_service.detect_risk(text, llm_config=resolved)
        except Exception:
            labels = []
        return labels or [], labels or []

    async def _save_prompt_snapshot(
        self,
        db: AsyncSession,
        message_id: int,
        user_id: int,
        session_id: int,
        mode: str,
        payload: dict,
    ) -> None:
        try:
            await chat_prompt_snapshot_crud.create_snapshot(
                db=db,
                message_id=message_id,
                user_id=user_id,
                session_id=session_id,
                mode=mode,
                payload=payload or {},
            )
        except Exception as exc:
            logger.warning(f"Prompt snapshot save failed: {exc}")

