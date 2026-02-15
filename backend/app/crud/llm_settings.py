
"""crud/llm_settings.py."""
from datetime import datetime
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.models.llm_settings import UserLLMSettings


class LLMSettingsCRUD:
    @staticmethod
    async def get_by_user_id(db: AsyncSession, user_id: int) -> Optional[UserLLMSettings]:
        """get_by_user_id ?????"""
        statement = select(UserLLMSettings).where(UserLLMSettings.user_id == user_id)
        result = await db.execute(statement)
        return result.scalar_one_or_none()

    @staticmethod
    async def upsert_for_user(
        db: AsyncSession,
        user_id: int,
        update_data: dict,
    ) -> UserLLMSettings:
        """upsert_for_user ?????"""
        settings_row = await LLMSettingsCRUD.get_by_user_id(db, user_id)
        now = datetime.utcnow()
        if not settings_row:
            settings_row = UserLLMSettings(user_id=user_id, created_at=now, updated_at=now)
            db.add(settings_row)

        for field, value in update_data.items():
            setattr(settings_row, field, value)

        settings_row.updated_at = now
        db.add(settings_row)
        await db.commit()
        await db.refresh(settings_row)
        return settings_row

    @staticmethod
    async def delete_for_user(db: AsyncSession, user_id: int) -> bool:
        """delete_for_user ?????"""
        settings_row = await LLMSettingsCRUD.get_by_user_id(db, user_id)
        if not settings_row:
            return False
        await db.delete(settings_row)
        await db.commit()
        return True


llm_settings_crud = LLMSettingsCRUD()
