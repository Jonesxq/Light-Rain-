"""聊天附件数据库操作模块 - 提供聊天附件的CRUD操作"""
from typing import List, Optional

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select, desc

from app.models.chat import ChatAttachment


class ChatAttachmentCRUD:
    """聊天附件CRUD操作类 - 管理聊天附件的数据库操作"""

    async def create_attachment(
        self,
        db: AsyncSession,
        user_id: int,
        file_name: str,
        file_type: str,
        file_size: int,
        file_path: str,
        extracted_text: Optional[str],
        chunks: Optional[list[str]],
    ) -> ChatAttachment:
        """创建新的聊天附件
        
        Args:
            db: 异步数据库会话
            user_id: 用户ID
            file_name: 文件名
            file_type: 文件类型
            file_size: 文件大小（字节）
            file_path: 文件存储路径
            extracted_text: 提取的文本内容
            chunks: 文本分块列表
            
        Returns:
            ChatAttachment: 创建的附件对象
        """
        attachment = ChatAttachment(
            user_id=user_id,
            file_name=file_name,
            file_type=file_type,
            file_size=file_size,
            file_path=file_path,
            extracted_text=extracted_text,
            chunks=chunks,
        )
        db.add(attachment)
        await db.commit()
        await db.refresh(attachment)
        return attachment

    async def list_attachments(self, db: AsyncSession, user_id: int) -> List[ChatAttachment]:
        """获取用户的所有附件
        
        Args:
            db: 异步数据库会话
            user_id: 用户ID
            
        Returns:
            List[ChatAttachment]: 附件列表，按创建时间倒序排列
        """
        statement = (
            select(ChatAttachment)
            .where(ChatAttachment.user_id == user_id)
            .order_by(desc(ChatAttachment.created_at))
        )
        result = await db.execute(statement)
        return list(result.scalars().all())

    async def get_attachment(self, db: AsyncSession, attachment_id: int) -> Optional[ChatAttachment]:
        """根据ID获取附件
        
        Args:
            db: 异步数据库会话
            attachment_id: 附件ID
            
        Returns:
            Optional[ChatAttachment]: 附件对象，如果不存在则返回None
        """
        return await db.get(ChatAttachment, attachment_id)

    async def delete_attachment(self, db: AsyncSession, attachment_id: int) -> bool:
        """删除附件
        
        Args:
            db: 异步数据库会话
            attachment_id: 附件ID
            
        Returns:
            bool: 删除成功返回True，否则返回False
        """
        attachment = await db.get(ChatAttachment, attachment_id)
        if not attachment:
            return False
        await db.delete(attachment)
        await db.commit()
        return True


chat_attachment_crud = ChatAttachmentCRUD()
