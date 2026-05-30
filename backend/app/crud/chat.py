"""聊天数据库操作模块 - 提供聊天会话和消息的CRUD操作"""
import json
from datetime import datetime
from typing import List, Optional

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select, desc
from sqlalchemy import delete, or_

from app.core.redis import redis_manager
from app.models.chat import ChatSession, ChatMessage, ChatRole


class ChatCRUD:
    """聊天CRUD操作类 - 管理聊天会话和消息的数据库操作"""
    
    # --------------------
    # Cache helpers（序列化/反序列化）
    # --------------------

    def _serialize_session(self, session: ChatSession) -> dict:
        """序列化聊天会话对象为字典，用于Redis缓存
        
        Args:
            session: 聊天会话对象
            
        Returns:
            dict: 序列化后的会话字典
        """
        return {
            "id": session.id,
            "user_id": session.user_id,
            "title": session.title,
            "is_deleted": session.is_deleted,
            "is_pinned": session.is_pinned,
            "is_archived": getattr(session, "is_archived", False),
            "tags": list(getattr(session, "tags", []) or []),
            "created_at": session.created_at.isoformat() if session.created_at else None,
            "updated_at": session.updated_at.isoformat() if session.updated_at else None,
        }

    def _serialize_message(self, message: ChatMessage) -> dict:
        """序列化聊天消息对象为字典，用于Redis缓存
        
        Args:
            message: 聊天消息对象
            
        Returns:
            dict: 序列化后的消息字典
        """
        return {
            "id": message.id,
            "session_id": message.session_id,
            "kb_id": message.kb_id,
            "role": message.role.value if isinstance(message.role, ChatRole) else message.role,
            "content": message.content,
            "model_name": message.model_name,
            "token_count": message.token_count,
            "sources": message.sources,
            "disclaimer_codes": list(getattr(message, "disclaimer_codes", []) or []),
            "risk_tags": list(getattr(message, "risk_tags", []) or []),
            "is_favorite": bool(getattr(message, "is_favorite", False)),
            "edited_at": message.edited_at.isoformat() if message.edited_at else None,
            "created_at": message.created_at.isoformat() if message.created_at else None,
        }

    def _session_from_cache(self, data: dict) -> ChatSession:
        """从缓存数据反序列化聊天会话对象
        
        Args:
            data: 缓存中的会话字典数据
            
        Returns:
            ChatSession: 反序列化后的会话对象
        """
        return ChatSession(
            id=data.get("id"),
            user_id=data.get("user_id"),
            title=data.get("title") or "New Chat",
            is_deleted=bool(data.get("is_deleted", False)),
            is_pinned=bool(data.get("is_pinned", False)),
            is_archived=bool(data.get("is_archived", False)),
            tags=list(data.get("tags") or []),
            created_at=datetime.fromisoformat(data["created_at"]) if data.get("created_at") else None,
            updated_at=datetime.fromisoformat(data["updated_at"]) if data.get("updated_at") else None,
        )

    def _message_from_cache(self, data: dict) -> ChatMessage:
        """从缓存数据反序列化聊天消息对象
        
        Args:
            data: 缓存中的消息字典数据
            
        Returns:
            ChatMessage: 反序列化后的消息对象
        """
        return ChatMessage(
            id=data.get("id"),
            session_id=data.get("session_id"),
            kb_id=data.get("kb_id"),
            role=ChatRole(data.get("role")) if data.get("role") else ChatRole.USER,
            content=data.get("content") or "",
            model_name=data.get("model_name"),
            token_count=data.get("token_count", 0),
            sources=data.get("sources"),
            disclaimer_codes=list(data.get("disclaimer_codes") or []),
            risk_tags=list(data.get("risk_tags") or []),
            is_favorite=bool(data.get("is_favorite", False)),
            edited_at=datetime.fromisoformat(data["edited_at"]) if data.get("edited_at") else None,
            created_at=datetime.fromisoformat(data["created_at"]) if data.get("created_at") else None,
        )

    # ========== 会话操作 ==========

    async def create_session(self, db: AsyncSession, user_id: int, title: str = "New Chat") -> ChatSession:
        """创建新的聊天会话
        
        Args:
            db: 异步数据库会话
            user_id: 用户ID
            title: 会话标题，默认为"New Chat"
            
        Returns:
            ChatSession: 创建的会话对象
        """
        session = ChatSession(user_id=user_id, title=title)
        db.add(session)
        await db.commit()
        await db.refresh(session)
        # 失效会话列表缓存
        await redis_manager.delete_pattern_async(f"chat:sessions:{user_id}:*")
        return session

    async def get_user_sessions(
        self,
        db: AsyncSession,
        user_id: int,
        skip: int = 0,
        limit: int = 20,
        q: Optional[str] = None,
        include_archived: bool = False,
    ) -> List[ChatSession]:
        """获取用户的聊天会话列表
        
        优先从Redis缓存获取，缓存未命中则查询数据库
        
        Args:
            db: 异步数据库会话
            user_id: 用户ID
            skip: 跳过的记录数，用于分页
            limit: 返回的最大记录数
            q: 搜索关键词，用于标题搜索
            include_archived: 是否包含已归档的会话
            
        Returns:
            List[ChatSession]: 聊天会话列表
        """
        cache_key = f"chat:sessions:{user_id}:{skip}:{limit}:{include_archived}:{q or ''}"
        try:
            cached = await redis_manager.get_async(cache_key)
            if cached:
                data = json.loads(cached)
                return [self._session_from_cache(item) for item in data]
        except Exception:
            # 缓存异常不影响主流程
            pass

        # 缓存未命中则回源数据库
        statement = select(ChatSession).where(
            ChatSession.user_id == user_id,
            or_(ChatSession.is_deleted == False, ChatSession.is_deleted.is_(None)),
        )
        if not include_archived:
            # 兼容历史数据 is_archived 为空的情况
            statement = statement.where(
                or_(ChatSession.is_archived == False, ChatSession.is_archived.is_(None))
            )
        if q:
            statement = statement.where(ChatSession.title.ilike(f"%{q}%"))
        statement = (
            statement
            .order_by(desc(ChatSession.is_pinned), desc(ChatSession.updated_at))
            .offset(skip)
            .limit(limit)
        )
        result = await db.execute(statement)
        sessions = list(result.scalars().all())
        # 兜底 tags，避免返回 None 导致校验失败
        for session in sessions:
            session.tags = list(session.tags or [])
        try:
            payload = json.dumps([self._serialize_session(s) for s in sessions], ensure_ascii=False)
            await redis_manager.set_async(cache_key, payload)
        except Exception:
            pass
        return sessions

    async def get_session(self, db: AsyncSession, session_id: int) -> Optional[ChatSession]:
        """根据ID获取聊天会话
        
        Args:
            db: 异步数据库会话
            session_id: 会话ID
            
        Returns:
            Optional[ChatSession]: 会话对象，如果不存在则返回None
        """
        return await db.get(ChatSession, session_id)

    async def update_session_time(self, db: AsyncSession, session_id: int):
        """更新会话的最后更新时间
        
        Args:
            db: 异步数据库会话
            session_id: 会话ID
        """
        session = await self.get_session(db, session_id)
        if session:
            session.updated_at = datetime.utcnow()
            db.add(session)
            await db.commit()
            # 失效会话列表缓存
            await redis_manager.delete_pattern_async(f"chat:sessions:{session.user_id}:*")

    async def update_session(
        self,
        db: AsyncSession,
        session_id: int,
        title: Optional[str] = None,
        is_pinned: Optional[bool] = None,
        is_archived: Optional[bool] = None,
        tags: Optional[List[str]] = None,
    ) -> Optional[ChatSession]:
        """更新聊天会话信息
        
        Args:
            db: 异步数据库会话
            session_id: 会话ID
            title: 新的会话标题
            is_pinned: 是否置顶
            is_archived: 是否归档
            tags: 标签列表
            
        Returns:
            Optional[ChatSession]: 更新后的会话对象，如果不存在则返回None
        """
        session = await self.get_session(db, session_id)
        if not session:
            return None
        if title is not None:
            session.title = title
        if is_pinned is not None:
            session.is_pinned = bool(is_pinned)
        if is_archived is not None:
            session.is_archived = bool(is_archived)
        if tags is not None:
            session.tags = list(tags)
        # 兜底 tags，避免 NULL 传播到响应
        if session.tags is None:
            session.tags = []
        session.updated_at = datetime.utcnow()
        db.add(session)
        await db.commit()
        await db.refresh(session)
        await redis_manager.delete_pattern_async(f"chat:sessions:{session.user_id}:*")
        return session

    async def delete_session(self, db: AsyncSession, session_id: int, user_id: int) -> bool:
        """删除聊天会话（软删除）
        
        Args:
            db: 异步数据库会话
            session_id: 会话ID
            user_id: 用户ID，用于验证权限
            
        Returns:
            bool: 删除成功返回True，否则返回False
        """
        session = await self.get_session(db, session_id)
        if not session or session.user_id != user_id:
            return False
        session.is_deleted = True
        db.add(session)
        await db.commit()
        # 失效会话列表缓存
        await redis_manager.delete_pattern_async(f"chat:sessions:{user_id}:*")
        return True

    # ========== 消息操作 ==========

    async def create_message(
            self,
            db: AsyncSession,
            session_id: int,
            role: ChatRole,
            content: str,
            kb_id: Optional[int] = None,
            model_name: Optional[str] = None,
            token_count: Optional[int] = 0,
            sources: Optional[list[dict]] = None,
            disclaimer_codes: Optional[list[str]] = None,
            risk_tags: Optional[list[str]] = None,
    ) -> ChatMessage:
        """创建新的聊天消息
        
        Args:
            db: 异步数据库会话
            session_id: 会话ID
            role: 消息角色（用户或助手）
            content: 消息内容
            kb_id: 关联的知识库ID
            model_name: 使用的模型名称
            token_count: 消耗的token数量
            sources: 引用来源列表
            disclaimer_codes: 免责声明代码列表
            risk_tags: 风险标签列表
            
        Returns:
            ChatMessage: 创建的消息对象
        """
        message = ChatMessage(
            session_id=session_id,
            role=role,
            content=content,
            kb_id=kb_id,
            model_name=model_name,
            token_count=token_count,
            sources=sources,
            disclaimer_codes=disclaimer_codes or [],
            risk_tags=risk_tags or [],
        )
        db.add(message)
        await db.commit()
        await db.refresh(message)
        # 失效消息列表缓存
        await redis_manager.delete_async(f"chat:messages:{session_id}")
        return message

    async def get_message(self, db: AsyncSession, message_id: int) -> Optional[ChatMessage]:
        """根据ID获取聊天消息
        
        Args:
            db: 异步数据库会话
            message_id: 消息ID
            
        Returns:
            Optional[ChatMessage]: 消息对象，如果不存在则返回None
        """
        return await db.get(ChatMessage, message_id)

    async def set_message_favorite(
        self,
        db: AsyncSession,
        message_id: int,
        is_favorite: bool
    ) -> Optional[ChatMessage]:
        """设置消息是否收藏
        
        Args:
            db: 异步数据库会话
            message_id: 消息ID
            is_favorite: 是否收藏
            
        Returns:
            Optional[ChatMessage]: 更新后的消息对象，如果不存在则返回None
        """
        message = await db.get(ChatMessage, message_id)
        if not message:
            return None
        message.is_favorite = bool(is_favorite)
        db.add(message)
        await db.commit()
        await db.refresh(message)
        await redis_manager.delete_async(f"chat:messages:{message.session_id}")
        return message

    async def update_message_content(
        self,
        db: AsyncSession,
        message_id: int,
        content: str
    ) -> Optional[ChatMessage]:
        """更新消息内容
        
        Args:
            db: 异步数据库会话
            message_id: 消息ID
            content: 新的消息内容
            
        Returns:
            Optional[ChatMessage]: 更新后的消息对象，如果不存在则返回None
        """
        message = await db.get(ChatMessage, message_id)
        if not message:
            return None
        message.content = content
        message.edited_at = datetime.utcnow()
        db.add(message)
        await db.commit()
        await db.refresh(message)
        await redis_manager.delete_async(f"chat:messages:{message.session_id}")
        return message

    async def delete_messages_after(self, db: AsyncSession, session_id: int, message_id: int) -> List[int]:
        """删除指定消息之后的所有消息
        
        Args:
            db: 异步数据库会话
            session_id: 会话ID
            message_id: 消息ID，删除此消息之后的所有消息
            
        Returns:
            List[int]: 被删除的消息ID列表
        """
        messages = await self.get_session_messages(db, session_id)
        if not messages:
            return []
        idx = next((i for i, msg in enumerate(messages) if msg.id == message_id), None)
        if idx is None:
            return []
        delete_ids = [msg.id for msg in messages[idx + 1:] if msg.id is not None]
        if not delete_ids:
            return []
        await db.execute(delete(ChatMessage).where(ChatMessage.id.in_(delete_ids)))
        await db.commit()
        await redis_manager.delete_async(f"chat:messages:{session_id}")
        return delete_ids

    async def get_session_messages(self, db: AsyncSession, session_id: int) -> List[ChatMessage]:
        """获取会话的所有消息
        
        优先从Redis缓存获取，缓存未命中则查询数据库
        
        Args:
            db: 异步数据库会话
            session_id: 会话ID
            
        Returns:
            List[ChatMessage]: 消息列表，按创建时间排序
        """
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
