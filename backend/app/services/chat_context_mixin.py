"""Context helpers for chat service."""

from typing import List, Optional

from langchain_core.messages import HumanMessage, AIMessage, SystemMessage, BaseMessage
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logger import logger_manager
from app.crud.chat import chat_crud
from app.crud.chat_prompt_snapshot import chat_prompt_snapshot_crud
from app.models.chat import ChatRole, ChatSession, ChatMessage
from app.services.safety import safety_service
from app.services.temp_context import temp_context_service

logger = logger_manager.get_logger(__name__)


class ChatContextMixin:
    """Chat context helpers."""

    async def _auto_rename_session(self, db: AsyncSession, session: ChatSession, user_msg: str):
        """_auto_rename_session ?????"""
        if session.title in {"New Chat", "新对话"}:
            new_title = user_msg[:15]
            session.title = new_title
            db.add(session)
            await db.commit()

    async def _build_langchain_history(self, db: AsyncSession, session_id: int, limit: int = 10) -> List[BaseMessage]:
        # 1) 获取历史消息
        """_build_langchain_history ?????"""
        db_messages = await chat_crud.get_session_messages(db, session_id)

        # 2) 排除最后一条（当前用户输入已在流程中单独处理）
        if db_messages and db_messages[-1].role == ChatRole.USER:
             db_messages = db_messages[:-1]

        # 3) 截取最近 N 条
        recent_db_msgs = db_messages[-limit:]

        langchain_msgs = []

        # 4) 映射为 LangChain Message 对象
        for msg in recent_db_msgs:
            if msg.role == ChatRole.USER:
                langchain_msgs.append(HumanMessage(content=msg.content))
            elif msg.role == ChatRole.ASSISTANT:
                langchain_msgs.append(AIMessage(content=msg.content))
            elif msg.role == ChatRole.SYSTEM:
                langchain_msgs.append(SystemMessage(content=msg.content))

        return langchain_msgs

    async def _get_temp_context(self, db: AsyncSession, user_id: int, query: str) -> str:
        """_get_temp_context ?????"""
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
        """_get_message_and_session_for_user ?????"""
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
        """Return (disclaimer_codes, risk_tags)."""
        if not text:
            return [], []
        try:
            if resolved is None:
                resolved = await self._resolve_user_llm_config(db, user_id, model)
            labels = await safety_service.detect_risk(text, llm_config=resolved)
        except Exception:
            labels = []
        # disclaimer codes follow labels
        codes = labels or []
        return codes, labels or []

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
