"""crud/chat_attachment.py."""
from typing import List, Optional

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select, desc

from app.models.chat import ChatAttachment


class ChatAttachmentCRUD:
    """ChatAttachmentCRUD ??"""

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
        """create_attachment ?????"""
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
        """list_attachments ?????"""
        statement = (
            select(ChatAttachment)
            .where(ChatAttachment.user_id == user_id)
            .order_by(desc(ChatAttachment.created_at))
        )
        result = await db.execute(statement)
        return list(result.scalars().all())

    async def get_attachment(self, db: AsyncSession, attachment_id: int) -> Optional[ChatAttachment]:
        """get_attachment ?????"""
        return await db.get(ChatAttachment, attachment_id)

    async def delete_attachment(self, db: AsyncSession, attachment_id: int) -> bool:
        """delete_attachment ?????"""
        attachment = await db.get(ChatAttachment, attachment_id)
        if not attachment:
            return False
        await db.delete(attachment)
        await db.commit()
        return True


chat_attachment_crud = ChatAttachmentCRUD()
