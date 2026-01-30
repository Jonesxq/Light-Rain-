"""聊天相关 CRUD：会话/消息读写，带 Redis 缓存"""
import json
from datetime import datetime
from typing import List, Optional

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select, desc

from app.core.redis import redis_manager
from app.models.chat import ChatSession, ChatMessage, ChatRole


class ChatCRUD:
    # --------------------
    # Cache helpers（序列化/反序列化）
    # --------------------

    def _serialize_session(self, session: ChatSession) -> dict:
        """将会话对象序列化为可缓存的字典"""
        return {
            "id": session.id,
            "user_id": session.user_id,
            "title": session.title,
            "is_deleted": session.is_deleted,
            "is_pinned": session.is_pinned,
            "created_at": session.created_at.isoformat() if session.created_at else None,
            "updated_at": session.updated_at.isoformat() if session.updated_at else None,
        }

    def _serialize_message(self, message: ChatMessage) -> dict:
        """将消息对象序列化为可缓存的字典"""
        return {
            "id": message.id,
            "session_id": message.session_id,
            "kb_id": message.kb_id,
            "role": message.role.value if isinstance(message.role, ChatRole) else message.role,
            "content": message.content,
            "model_name": message.model_name,
            "token_count": message.token_count,
            "sources": message.sources,
            "created_at": message.created_at.isoformat() if message.created_at else None,
        }

    def _session_from_cache(self, data: dict) -> ChatSession:
        """将缓存数据还原为会话对象"""
        return ChatSession(
            id=data.get("id"),
            user_id=data.get("user_id"),
            title=data.get("title") or "New Chat",
            is_deleted=bool(data.get("is_deleted", False)),
            is_pinned=bool(data.get("is_pinned", False)),
            created_at=datetime.fromisoformat(data["created_at"]) if data.get("created_at") else None,
            updated_at=datetime.fromisoformat(data["updated_at"]) if data.get("updated_at") else None,
        )

    def _message_from_cache(self, data: dict) -> ChatMessage:
        """将缓存数据还原为消息对象"""
        return ChatMessage(
            id=data.get("id"),
            session_id=data.get("session_id"),
            kb_id=data.get("kb_id"),
            role=ChatRole(data.get("role")) if data.get("role") else ChatRole.USER,
            content=data.get("content") or "",
            model_name=data.get("model_name"),
            token_count=data.get("token_count", 0),
            sources=data.get("sources"),
            created_at=datetime.fromisoformat(data["created_at"]) if data.get("created_at") else None,
        )

    # ========== Session Operations ==========

    async def create_session(self, db: AsyncSession, user_id: int, title: str = "New Chat") -> ChatSession:
        """创建会话并失效用户会话列表缓存"""
        session = ChatSession(user_id=user_id, title=title)
        db.add(session)
        await db.commit()
        await db.refresh(session)
        # 失效会话列表缓存
        await redis_manager.delete_pattern_async(f"chat:sessions:{user_id}:*")
        return session

    async def get_user_sessions(self, db: AsyncSession, user_id: int, skip: int = 0, limit: int = 20) -> List[
        ChatSession]:
        """获取用户的会话列表（优先走缓存，按更新时间倒序）"""
        cache_key = f"chat:sessions:{user_id}:{skip}:{limit}"
        try:
            cached = await redis_manager.get_async(cache_key)
            if cached:
                data = json.loads(cached)
                return [self._session_from_cache(item) for item in data]
        except Exception:
            # 缓存异常不影响主流程
            pass

        # 缓存未命中则回源数据库
        statement = (
            select(ChatSession)
            .where(ChatSession.user_id == user_id, ChatSession.is_deleted == False)
            .order_by(desc(ChatSession.updated_at))
            .offset(skip)
            .limit(limit)
        )
        result = await db.execute(statement)
        sessions = list(result.scalars().all())
        try:
            payload = json.dumps([self._serialize_session(s) for s in sessions], ensure_ascii=False)
            await redis_manager.set_async(cache_key, payload)
        except Exception:
            pass
        return sessions

    async def get_session(self, db: AsyncSession, session_id: int) -> Optional[ChatSession]:
        """按 ID 获取会话（不走缓存）"""
        return await db.get(ChatSession, session_id)

    async def update_session_time(self, db: AsyncSession, session_id: int):
        """更新会话的最后活跃时间"""
        session = await self.get_session(db, session_id)
        if session:
            session.updated_at = datetime.utcnow()
            db.add(session)
            await db.commit()

    async def delete_session(self, db: AsyncSession, session_id: int, user_id: int) -> bool:
        """软删除会话（仅标记 is_deleted）"""
        session = await self.get_session(db, session_id)
        if not session or session.user_id != user_id:
            return False
        session.is_deleted = True
        db.add(session)
        await db.commit()
        # 失效会话列表缓存
        await redis_manager.delete_pattern_async(f"chat:sessions:{user_id}:*")
        return True

    # ========== Message Operations ==========

    async def create_message(
            self,
            db: AsyncSession,
            session_id: int,
            role: ChatRole,
            content: str,
            kb_id: Optional[int] = None,  # 新增这个参数
            model_name: Optional[str] = None,
            token_count: Optional[int] = 0,
            sources: Optional[list[dict]] = None
    ) -> ChatMessage:
        """创建消息并失效该会话消息缓存"""
        message = ChatMessage(
            session_id=session_id,
            role=role,
            content=content,
            kb_id=kb_id,  # 确保赋值给模型对象
            model_name=model_name,
            token_count=token_count,
            sources=sources
        )
        db.add(message)
        await db.commit()
        await db.refresh(message)
        # 失效消息列表缓存
        await redis_manager.delete_async(f"chat:messages:{session_id}")
        return message

    async def get_session_messages(self, db: AsyncSession, session_id: int) -> List[ChatMessage]:
        """获取某会话消息（优先缓存，按创建时间正序）"""
        cache_key = f"chat:messages:{session_id}"
        try:
            cached = await redis_manager.get_async(cache_key)
            if cached:
                data = json.loads(cached)
                return [self._message_from_cache(item) for item in data]
        except Exception:
            pass

        # 缓存未命中则回源数据库
        statement = (
            select(ChatMessage)
            .where(ChatMessage.session_id == session_id)
            .order_by(ChatMessage.created_at.asc())
        )
        result = await db.execute(statement)
        messages = list(result.scalars().all())
        try:
            payload = json.dumps([self._serialize_message(m) for m in messages], ensure_ascii=False)
            await redis_manager.set_async(cache_key, payload)
        except Exception:
            pass
        return messages


chat_crud = ChatCRUD()
