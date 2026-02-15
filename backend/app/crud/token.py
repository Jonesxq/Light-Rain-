
"""crud/token.py."""
import secrets
from datetime import datetime, timedelta
from typing import Optional, List
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select
from app.models.token import RefreshToken, VerificationCode

class RefreshTokenCRUD:
    
    @staticmethod
    async def create(
        db: AsyncSession,
        user_id: int,
        token: str,
        expires_at: datetime,
        device_name: Optional[str] = None,
        device_type: Optional[str] = None,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
    ) -> RefreshToken:
        """create ?????"""
        db_token = RefreshToken(
            user_id=user_id,
            token=token,
            expires_at=expires_at,
            device_name=device_name,
            device_type=device_type,
            ip_address=ip_address,
            user_agent=user_agent,
        )
        
        db.add(db_token)
        await db.commit()
        await db.refresh(db_token)
        return db_token
    
    @staticmethod
    async def get_by_token(db: AsyncSession, token: str) -> Optional[RefreshToken]:
        """get_by_token ?????"""
        statement = select(RefreshToken).where(
            RefreshToken.token == token,
            RefreshToken.is_revoked == False
        )
        result = await db.execute(statement)
        return result.scalar_one_or_none()
    
    @staticmethod
    async def get_user_tokens(
        db: AsyncSession,
        user_id: int,
        include_revoked: bool = False
    ) -> List[RefreshToken]:
        """get_user_tokens ?????"""
        statement = select(RefreshToken).where(RefreshToken.user_id == user_id)
        
        if not include_revoked:
            statement = statement.where(RefreshToken.is_revoked == False)
        
        result = await db.execute(statement)
        return list(result.scalars().all())
    
    @staticmethod
    async def update_last_used(db: AsyncSession, token_id: int) -> Optional[RefreshToken]:
        """update_last_used ?????"""
        db_token = await db.get(RefreshToken, token_id)
        if not db_token:
            return None
        
        db_token.last_used_at = datetime.utcnow()
        db.add(db_token)
        await db.commit()
        await db.refresh(db_token)
        return db_token
    
    @staticmethod
    async def revoke(db: AsyncSession, token: str) -> bool:
        """revoke ?????"""
        db_token = await RefreshTokenCRUD.get_by_token(db, token)
        if not db_token:
            return False
        
        db_token.revoke()
        db.add(db_token)
        await db.commit()
        return True
    
    @staticmethod
    async def revoke_user_tokens(db: AsyncSession, user_id: int) -> int:
        """revoke_user_tokens ?????"""
        tokens = await RefreshTokenCRUD.get_user_tokens(db, user_id, include_revoked=False)
        
        count = 0
        for token in tokens:
            token.revoke()
            db.add(token)
            count += 1
        
        await db.commit()
        return count
    
    @staticmethod
    async def cleanup_expired(db: AsyncSession) -> int:
        """cleanup_expired ?????"""
        statement = select(RefreshToken).where(
            RefreshToken.expires_at < datetime.utcnow(),
            RefreshToken.is_revoked == False
        )
        result = await db.execute(statement)
        expired_tokens = list(result.scalars().all())
        
        count = 0
        for token in expired_tokens:
            token.revoke()
            db.add(token)
            count += 1
        
        await db.commit()
        return count


class VerificationCodeCRUD:
    
    @staticmethod
    def generate_code(length: int = 6) -> str:
        """generate_code ???"""
        return "".join([str(secrets.randbelow(10)) for _ in range(length)])
    
    @staticmethod
    async def create(
        db: AsyncSession,
        user_id: int,
        code_type: str,
        expiration_minutes: int = 60,
        max_attempts: int = 5,
    ) -> VerificationCode:
        """create ?????"""
        code = VerificationCodeCRUD.generate_code()
        
        db_code = VerificationCode(
            user_id=user_id,
            code=code,
            code_type=code_type,
            expires_at=datetime.utcnow() + timedelta(minutes=expiration_minutes),
            max_attempts=max_attempts,
        )
        
        db.add(db_code)
        await db.commit()
        await db.refresh(db_code)
        return db_code
    
    @staticmethod
    async def get(
        db: AsyncSession,
        user_id: int,
        code: str,
        code_type: str
    ) -> Optional[VerificationCode]:
        """get ?????"""
        statement = select(VerificationCode).where(
            VerificationCode.user_id == user_id,
            VerificationCode.code == code,
            VerificationCode.code_type == code_type,
            VerificationCode.is_used == False
        )
        result = await db.execute(statement)
        return result.scalar_one_or_none()
    
    @staticmethod
    async def verify(
        db: AsyncSession,
        user_id: int,
        code: str,
        code_type: str
    ) -> Optional[VerificationCode]:
        """verify ?????"""
        db_code = await VerificationCodeCRUD.get(db, user_id, code, code_type)
        
        if not db_code:
            return None
        
        # 累加尝试次数（防止暴力破解）
        db_code.increment_attempts()
        db.add(db_code)
        await db.commit()
        
        # 校验是否过期或超次数
        if not db_code.is_valid():
            return None
        
        # 标记为已使用
        db_code.mark_as_used()
        db.add(db_code)
        await db.commit()
        await db.refresh(db_code)
        
        return db_code
    
    @staticmethod
    async def get_latest(
        db: AsyncSession,
        user_id: int,
        code_type: str
    ) -> Optional[VerificationCode]:
        """get_latest ?????"""
        statement = select(VerificationCode).where(
            VerificationCode.user_id == user_id,
            VerificationCode.code_type == code_type
        ).order_by(VerificationCode.created_at.desc())
        
        result = await db.execute(statement)
        return result.scalar_one_or_none()
    
    @staticmethod
    async def invalidate_user_codes(db: AsyncSession, user_id: int, code_type: str) -> int:
        """invalidate_user_codes ?????"""
        statement = select(VerificationCode).where(
            VerificationCode.user_id == user_id,
            VerificationCode.code_type == code_type,
            VerificationCode.is_used == False
        )
        result = await db.execute(statement)
        codes = list(result.scalars().all())
        
        count = 0
        for code in codes:
            code.mark_as_used()
            db.add(code)
            count += 1
        
        await db.commit()
        return count
    
    @staticmethod
    async def cleanup_expired(db: AsyncSession) -> int:
        """cleanup_expired ?????"""
        statement = select(VerificationCode).where(
            VerificationCode.expires_at < datetime.utcnow(),
            VerificationCode.is_used == False
        )
        result = await db.execute(statement)
        expired_codes = list(result.scalars().all())
        
        count = 0
        for code in expired_codes:
            code.mark_as_used()
            db.add(code)
            count += 1
        
        await db.commit()
        return count

    @staticmethod
    async def delete_user_codes(
        db: AsyncSession,
        user_id: int,
        code_type: Optional[str] = None
    ) -> int:
        """delete_user_codes ?????"""
        statement = select(VerificationCode).where(VerificationCode.user_id == user_id)
        if code_type:
            statement = statement.where(VerificationCode.code_type == code_type)
        result = await db.execute(statement)
        codes = list(result.scalars().all())

        count = 0
        for code in codes:
            await db.delete(code)
            count += 1

        if count:
            await db.commit()
        return count


# Createglobalinstance
refresh_token_crud = RefreshTokenCRUD()
verification_code_crud = VerificationCodeCRUD()

