"""聊天服务上下文管理模块"""

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
    """聊天上下文管理Mixin：提供会话历史、临时上下文、风险检测等功能"""

    async def _auto_rename_session(self, db: AsyncSession, session: ChatSession, user_msg: str):
        """自动重命名会话（当会话标题为默认名称时）
        
        Args:
            db: 数据库会话
            session: 会话对象
            user_msg: 用户消息内容
        """
        if session.title in {"New Chat", "新对话"}:
            new_title = user_msg[:15]
            session.title = new_title
            db.add(session)
            await db.commit()

    async def _build_langchain_history(self, db: AsyncSession, session_id: int, limit: int = 10) -> List[BaseMessage]:
        """构建LangChain格式的历史消息列表
        
        Args:
            db: 数据库会话
            session_id: 会话ID
            limit: 历史消息数量限制
            
        Returns:
            LangChain消息对象列表
        """
        db_messages = await chat_crud.get_session_messages(db, session_id)

        if db_messages and db_messages[-1].role == ChatRole.USER:
             db_messages = db_messages[:-1]

        recent_db_msgs = db_messages[-limit:]

        langchain_msgs = []

        for msg in recent_db_msgs:
            if msg.role == ChatRole.USER:
                langchain_msgs.append(HumanMessage(content=msg.content))
            elif msg.role == ChatRole.ASSISTANT:
                langchain_msgs.append(AIMessage(content=msg.content))
            elif msg.role == ChatRole.SYSTEM:
                langchain_msgs.append(SystemMessage(content=msg.content))

        return langchain_msgs

    async def _get_temp_context(self, db: AsyncSession, user_id: int, query: str) -> str:
        """获取临时上下文（用于临时上下文服务）
        
        Args:
            db: 数据库会话
            user_id: 用户ID
            query: 查询文本
            
        Returns:
            临时上下文文本
        """
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
        """获取消息和对应的会话（验证用户权限）
        
        Args:
            db: 数据库会话
            user_id: 用户ID
            message_id: 消息ID
            
        Returns:
            元组(消息对象, 会话对象)
            
        Raises:
            ValueError: 当消息不存在或用户无权访问时
        """
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
        """获取风险信息（免责声明代码和风险标签）
        
        Args:
            db: 数据库会话
            user_id: 用户ID
            text: 待检测的文本
            model: 模型名称
            resolved: 已解析的LLM配置（可选）
            
        Returns:
            元组(免责声明代码列表, 风险标签列表)
        """
        if not text:
            return [], []
        try:
            if resolved is None:
                resolved = await self._resolve_user_llm_config(db, user_id, model)
            labels = await safety_service.detect_risk(text, llm_config=resolved)
        except Exception:
            labels = []
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
        """保存提示词快照（用于调试和分析）
        
        Args:
            db: 数据库会话
            message_id: 消息ID
            user_id: 用户ID
            session_id: 会话ID
            mode: 模式
            payload: 快照数据
        """
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
