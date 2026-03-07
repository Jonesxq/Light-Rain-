"""聊天提示快照数据库操作模块 - 提供聊天提示快照的CRUD操作"""

from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.models.chat import ChatPromptSnapshot


class ChatPromptSnapshotCRUD:
    """聊天提示快照CRUD操作类 - 管理聊天提示快照的数据库操作"""

    async def create_snapshot(
        self,
        db: AsyncSession,
        message_id: int,
        user_id: int,
        session_id: int,
        mode: str,
        payload: dict,
    ) -> ChatPromptSnapshot:
        """创建新的聊天提示快照
        
        Args:
            db: 异步数据库会话
            message_id: 消息ID
            user_id: 用户ID
            session_id: 会话ID
            mode: 模式
            payload: 快照数据
            
        Returns:
            ChatPromptSnapshot: 创建的快照对象
        """
        snapshot = ChatPromptSnapshot(
            message_id=message_id,
            user_id=user_id,
            session_id=session_id,
            mode=mode,
            payload=payload,
        )
        db.add(snapshot)
        await db.commit()
        await db.refresh(snapshot)
        return snapshot

    async def get_by_message_id(
        self,
        db: AsyncSession,
        message_id: int,
    ) -> Optional[ChatPromptSnapshot]:
        """根据消息ID获取提示快照
        
        Args:
            db: 异步数据库会话
            message_id: 消息ID
            
        Returns:
            Optional[ChatPromptSnapshot]: 快照对象，如果不存在则返回None
        """
        statement = select(ChatPromptSnapshot).where(ChatPromptSnapshot.message_id == message_id)
        result = await db.execute(statement)
        return result.scalars().first()


chat_prompt_snapshot_crud = ChatPromptSnapshotCRUD()
