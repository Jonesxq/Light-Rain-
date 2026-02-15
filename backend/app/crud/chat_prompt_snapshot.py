"""CRUD for chat prompt snapshots."""

from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.models.chat import ChatPromptSnapshot


class ChatPromptSnapshotCRUD:
    """ChatPromptSnapshotCRUD ??"""

    async def create_snapshot(
        self,
        db: AsyncSession,
        message_id: int,
        user_id: int,
        session_id: int,
        mode: str,
        payload: dict,
    ) -> ChatPromptSnapshot:
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
        statement = select(ChatPromptSnapshot).where(ChatPromptSnapshot.message_id == message_id)
        result = await db.execute(statement)
        return result.scalars().first()


chat_prompt_snapshot_crud = ChatPromptSnapshotCRUD()
