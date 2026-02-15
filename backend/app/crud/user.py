
"""crud/user.py."""
from datetime import datetime, timedelta
from typing import Optional, List
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.models.user import User
from app.schemas.user import UserCreate, UserUpdate
from app.core.security import get_password_hash, verify_password
import secrets

class UserCRUD:
    
    @staticmethod
    async def get_by_id(db: AsyncSession, user_id: int) -> Optional[User]:
        """get_by_id ?????"""
        result = await db.get(User, user_id)
        return result
    
    @staticmethod
    async def get_by_username(db: AsyncSession, username: str) -> Optional[User]:
        """get_by_username ?????"""
        statement = select(User).where(User.username == username)
        result = await db.execute(statement)
        return result.scalar_one_or_none()
    
    @staticmethod
    async def get_by_email(db: AsyncSession, email: str) -> Optional[User]:
        """get_by_email ?????"""
        statement = select(User).where(User.email == email)
        result = await db.execute(statement)
        return result.scalar_one_or_none()
    
    @staticmethod
    async def get_all(db: AsyncSession, skip: int = 0, limit: int = 100) -> List[User]:
        """get_all ?????"""
        statement = select(User).offset(skip).limit(limit)
        result = await db.execute(statement)
        return list(result.scalars().all())
    
    @staticmethod
    async def create(db: AsyncSession, user_create: UserCreate) -> User:
        """create ?????"""
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
        """update ?????"""
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
        """delete ?????"""
        db_user = await UserCRUD.get_by_id(db, user_id)
        if not db_user:
            return False
        
        await db.delete(db_user)
        await db.commit()
        return True
    
    @staticmethod
    async def authenticate(db: AsyncSession, username: str, password: str) -> Optional[User]:
        # 1) 先用用户名尝试
        """authenticate ?????"""
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
        """verify_email ?????"""
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
        """change_password ?????"""
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

