"""令牌数据库操作模块 - 提供刷新令牌和验证码的CRUD操作"""
import secrets
from datetime import datetime, timedelta
from typing import Optional, List
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select
from app.models.token import RefreshToken, VerificationCode


class RefreshTokenCRUD:
    """刷新令牌CRUD操作类 - 管理用户刷新令牌的数据库操作"""
    
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
        """创建新的刷新令牌
        
        Args:
            db: 异步数据库会话
            user_id: 用户ID
            token: 刷新令牌字符串
            expires_at: 过期时间
            device_name: 设备名称
            device_type: 设备类型
            ip_address: IP地址
            user_agent: 用户代理
            
        Returns:
            RefreshToken: 创建的刷新令牌对象
        """
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
        """根据令牌字符串获取刷新令牌
        
        只返回未撤销的令牌
        
        Args:
            db: 异步数据库会话
            token: 刷新令牌字符串
            
        Returns:
            Optional[RefreshToken]: 刷新令牌对象，如果不存在或已撤销则返回None
        """
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
        """获取用户的所有刷新令牌
        
        Args:
            db: 异步数据库会话
            user_id: 用户ID
            include_revoked: 是否包含已撤销的令牌
            
        Returns:
            List[RefreshToken]: 刷新令牌列表
        """
        statement = select(RefreshToken).where(RefreshToken.user_id == user_id)
        
        if not include_revoked:
            statement = statement.where(RefreshToken.is_revoked == False)
        
        result = await db.execute(statement)
        return list(result.scalars().all())
    
    @staticmethod
    async def update_last_used(db: AsyncSession, token_id: int) -> Optional[RefreshToken]:
        """更新刷新令牌的最后使用时间
        
        Args:
            db: 异步数据库会话
            token_id: 令牌ID
            
        Returns:
            Optional[RefreshToken]: 更新后的令牌对象，如果不存在则返回None
        """
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
        """撤销刷新令牌
        
        Args:
            db: 异步数据库会话
            token: 刷新令牌字符串
            
        Returns:
            bool: 撤销成功返回True，否则返回False
        """
        db_token = await RefreshTokenCRUD.get_by_token(db, token)
        if not db_token:
            return False
        
        db_token.revoke()
        db.add(db_token)
        await db.commit()
        return True
    
    @staticmethod
    async def revoke_user_tokens(db: AsyncSession, user_id: int) -> int:
        """撤销用户的所有未撤销的刷新令牌
        
        Args:
            db: 异步数据库会话
            user_id: 用户ID
            
        Returns:
            int: 被撤销的令牌数量
        """
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
        """清理已过期但未撤销的刷新令牌
        
        Args:
            db: 异步数据库会话
            
        Returns:
            int: 被清理的令牌数量
        """
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
    """验证码CRUD操作类 - 管理用户验证码的数据库操作"""
    
    @staticmethod
    def generate_code(length: int = 6) -> str:
        """生成随机数字验证码
        
        Args:
            length: 验证码长度，默认为6位
            
        Returns:
            str: 生成的验证码字符串
        """
        return "".join([str(secrets.randbelow(10)) for _ in range(length)])
    
    @staticmethod
    async def create(
        db: AsyncSession,
        user_id: int,
        code_type: str,
        expiration_minutes: int = 60,
        max_attempts: int = 5,
    ) -> VerificationCode:
        """创建新的验证码
        
        Args:
            db: 异步数据库会话
            user_id: 用户ID
            code_type: 验证码类型
            expiration_minutes: 过期时间（分钟），默认为60分钟
            max_attempts: 最大尝试次数，默认为5次
            
        Returns:
            VerificationCode: 创建的验证码对象
        """
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
        """根据用户ID、验证码和类型获取未使用的验证码
        
        Args:
            db: 异步数据库会话
            user_id: 用户ID
            code: 验证码
            code_type: 验证码类型
            
        Returns:
            Optional[VerificationCode]: 验证码对象，如果不存在或已使用则返回None
        """
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
        """验证验证码
        
        会累加尝试次数，防止暴力破解。验证成功后标记为已使用。
        
        Args:
            db: 异步数据库会话
            user_id: 用户ID
            code: 验证码
            code_type: 验证码类型
            
        Returns:
            Optional[VerificationCode]: 验证成功返回验证码对象，失败返回None
        """
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
        """获取用户某类型的最新验证码
        
        Args:
            db: 异步数据库会话
            user_id: 用户ID
            code_type: 验证码类型
            
        Returns:
            Optional[VerificationCode]: 最新的验证码对象，如果不存在则返回None
        """
        statement = select(VerificationCode).where(
            VerificationCode.user_id == user_id,
            VerificationCode.code_type == code_type
        ).order_by(VerificationCode.created_at.desc())
        
        result = await db.execute(statement)
        return result.scalar_one_or_none()
    
    @staticmethod
    async def invalidate_user_codes(db: AsyncSession, user_id: int, code_type: str) -> int:
        """作废用户某类型的所有未使用验证码
        
        Args:
            db: 异步数据库会话
            user_id: 用户ID
            code_type: 验证码类型
            
        Returns:
            int: 被作废的验证码数量
        """
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
        """清理已过期但未使用的验证码
        
        Args:
            db: 异步数据库会话
            
        Returns:
            int: 被清理的验证码数量
        """
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
        """删除用户的验证码
        
        Args:
            db: 异步数据库会话
            user_id: 用户ID
            code_type: 验证码类型，如果为None则删除所有类型
            
        Returns:
            int: 被删除的验证码数量
        """
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


# 创建全局实例
refresh_token_crud = RefreshTokenCRUD()
verification_code_crud = VerificationCodeCRUD()
