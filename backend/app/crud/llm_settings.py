"""LLM设置数据库操作模块 - 提供用户LLM设置的CRUD操作"""
from datetime import datetime
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.models.llm_settings import UserLLMSettings


class LLMSettingsCRUD:
    """LLM设置CRUD操作类 - 管理用户LLM配置的数据库操作"""
    
    @staticmethod
    async def get_by_user_id(db: AsyncSession, user_id: int) -> Optional[UserLLMSettings]:
        """根据用户ID获取LLM设置
        
        Args:
            db: 异步数据库会话
            user_id: 用户ID
            
        Returns:
            Optional[UserLLMSettings]: LLM设置对象，如果不存在则返回None
        """
        statement = select(UserLLMSettings).where(UserLLMSettings.user_id == user_id)
        result = await db.execute(statement)
        return result.scalar_one_or_none()

    @staticmethod
    async def upsert_for_user(
        db: AsyncSession,
        user_id: int,
        update_data: dict,
    ) -> UserLLMSettings:
        """更新或创建用户的LLM设置
        
        如果用户设置不存在则创建，存在则更新
        
        Args:
            db: 异步数据库会话
            user_id: 用户ID
            update_data: 更新数据字典
            
        Returns:
            UserLLMSettings: 更新后的设置对象
        """
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
        """删除用户的LLM设置
        
        Args:
            db: 异步数据库会话
            user_id: 用户ID
            
        Returns:
            bool: 删除成功返回True，否则返回False
        """
        settings_row = await LLMSettingsCRUD.get_by_user_id(db, user_id)
        if not settings_row:
            return False
        await db.delete(settings_row)
        await db.commit()
        return True


llm_settings_crud = LLMSettingsCRUD()
