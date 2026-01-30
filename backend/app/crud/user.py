"""用户 CRUD：账户创建、查询、更新、删除与认证"""

from datetime import datetime, timedelta
from typing import Optional, List
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.models.user import User
from app.schemas.user import UserCreate, UserUpdate
from app.core.security import get_password_hash, verify_password
import secrets

class UserCRUD:
    """用户 CRUD（异步）"""
    
    @staticmethod
    async def get_by_id(db: AsyncSession, user_id: int) -> Optional[User]:
        """按 ID 获取用户"""
        result = await db.get(User, user_id)
        return result
    
    @staticmethod
    async def get_by_username(db: AsyncSession, username: str) -> Optional[User]:
        """按用户名获取用户"""
        statement = select(User).where(User.username == username)
        result = await db.execute(statement)
        return result.scalar_one_or_none()
    
    @staticmethod
    async def get_by_email(db: AsyncSession, email: str) -> Optional[User]:
        """按邮箱获取用户"""
        statement = select(User).where(User.email == email)
        result = await db.execute(statement)
        return result.scalar_one_or_none()
    
    @staticmethod
    async def get_all(db: AsyncSession, skip: int = 0, limit: int = 100) -> List[User]:
        """分页获取用户列表"""
        statement = select(User).offset(skip).limit(limit)
        result = await db.execute(statement)
        return list(result.scalars().all())
    
    @staticmethod
    async def create(db: AsyncSession, user_create: UserCreate) -> User:
        """创建用户（默认未验证邮箱）"""
        hashed_password = get_password_hash(user_create.password)
        
        db_user = User(
            username=user_create.username,
            email=user_create.email,
            hashed_password=hashed_password,
            is_verified=False,  # needEmailValidate
        )
        
        db.add(db_user)
        await db.commit()
        await db.refresh(db_user)
        return db_user
    
    @staticmethod
    async def update(db: AsyncSession, user_id: int, user_update: UserUpdate) -> Optional[User]:
        """更新用户信息（支持修改密码）"""
        db_user = await UserCRUD.get_by_id(db, user_id)
        if not db_user:
            return None
        
        update_data = user_update.model_dump(exclude_unset=True)
        
        # 如果更新密码，需要重新 hash
        if "password" in update_data:
            update_data["hashed_password"] = get_password_hash(update_data.pop("password"))
        
        for field, value in update_data.items():
            setattr(db_user, field, value)
        
        db_user.updated_at = datetime.utcnow()
        db.add(db_user)
        await db.commit()
        await db.refresh(db_user)
        return db_user
    
    @staticmethod
    async def delete(db: AsyncSession, user_id: int) -> bool:
        """删除用户（受外键约束影响）"""
        db_user = await UserCRUD.get_by_id(db, user_id)
        if not db_user:
            return False
        
        await db.delete(db_user)
        await db.commit()
        return True
    
    @staticmethod
    async def authenticate(db: AsyncSession, username: str, password: str) -> Optional[User]:
        """校验用户凭证（支持用户名/邮箱）"""
        # 1) 先用用户名尝试
        user = await UserCRUD.get_by_username(db, username)
        
        # 2) 用户名不存在则用邮箱尝试
        if not user:
            user = await UserCRUD.get_by_email(db, username)
        
        if not user:
            return None
        
        if not verify_password(password, user.hashed_password):
            return None
        
        # 3) 更新最近登录时间
        user.last_login_at = datetime.utcnow()
        db.add(user)
        await db.commit()
        
        return user
    
    @staticmethod
    async def verify_email(db: AsyncSession, user_id: int) -> Optional[User]:
        """标记邮箱已验证"""
        db_user = await UserCRUD.get_by_id(db, user_id)
        if not db_user:
            return None
        
        db_user.is_verified = True
        db.add(db_user)
        await db.commit()
        await db.refresh(db_user)
        return db_user
    
    @staticmethod
    async def change_password(db: AsyncSession, user_id: int, new_password: str) -> Optional[User]:
        """修改用户密码"""
        db_user = await UserCRUD.get_by_id(db, user_id)
        if not db_user:
            return None
        
        db_user.hashed_password = get_password_hash(new_password)
        db_user.updated_at = datetime.utcnow()
        db.add(db_user)
        await db.commit()
        await db.refresh(db_user)
        return db_user


# Createglobalinstance
user_crud = UserCRUD()

