"""认证服务模块 - 完整的JWT认证体系"""

from datetime import datetime, timedelta
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.security import security_manager
from app.crud.user import user_crud
from app.crud.token import refresh_token_crud, verification_code_crud
from app.models.user import User
from app.schemas.user import UserCreate, Token
from app.utils.email import email_service

class AuthService:
    """认证服务类：提供用户注册、登录、令牌刷新、邮箱验证、密码找回等功能"""
    
    @staticmethod
    def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
        """生成访问令牌（JWT）
        
        Args:
            data: 要编码的数据
            expires_delta: 过期时间增量（已废弃，使用配置中的值）
            
        Returns:
            JWT令牌字符串
        """
        # 由 security_manager 统一处理签名与过期时间
        token, _ = security_manager.create_access_token(data)
        return token
    
    @staticmethod
    def create_refresh_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
        """生成刷新令牌（JWT）
        
        Args:
            data: 要编码的数据
            expires_delta: 过期时间增量（已废弃，使用配置中的值）
            
        Returns:
            JWT刷新令牌字符串
        """
        # 刷新令牌生命周期更长，用于换取新的 access token
        token, _ = security_manager.create_refresh_token(data)
        return token
    
    @staticmethod
    async def register_user(
        db: AsyncSession,
        user_data: UserCreate,
        send_verification: bool = True
    ) -> User:
        """注册新用户（默认发送邮箱验证码）
        
        Args:
            db: 数据库会话
            user_data: 用户创建数据
            send_verification: 是否发送验证邮件
            
        Returns:
            创建的用户对象
            
        Raises:
            ValueError: 当用户名或邮箱已存在时
        """
        # 1) 校验用户名是否已存在
        if await user_crud.get_by_username(db, user_data.username):
            raise ValueError("Username already registered")
        
        # 2) 校验邮箱是否已存在
        if await user_crud.get_by_email(db, user_data.email):
            raise ValueError("Email already registered")
        
        # 3) 创建用户（默认未验证）
        user = await user_crud.create(db, user_data)
        
        # 4) 发送验证邮件（失败则清理用户和验证码，避免脏数据）
        if send_verification:
            try:
                await AuthService.send_verification_email(db, user)
            except Exception as e:
                # 邮件发送失败时的清理逻辑
                try:
                    await verification_code_crud.delete_user_codes(
                        db, user_id=user.id, code_type="email_verification"
                    )
                except Exception:
                    pass
                try:
                    await user_crud.delete(db, user.id)
                except Exception:
                    pass
                raise e
        
        return user
    
    @staticmethod
    async def send_verification_email(db: AsyncSession, user: User) -> None:
        """发送邮箱验证码
        
        Args:
            db: 数据库会话
            user: 用户对象
        """
        # 1) 生成验证码并写入数据库
        code = await verification_code_crud.create(
            db,
            user_id=user.id,
            code_type="email_verification",
            expiration_minutes=60
        )
        
        # 2) 调用邮件服务发送模板邮件
        await email_service.send_email(
            subject="Email Verification",
            recipient=user.email,
            template="verification",
            username=user.username,
            code=code.code
        )
    
    @staticmethod
    async def verify_email(db: AsyncSession, user_id: int, code: str) -> bool:
        """校验邮箱验证码并标记用户为已验证
        
        Args:
            db: 数据库会话
            user_id: 用户ID
            code: 验证码
            
        Returns:
            验证是否成功
        """
        # 1) 校验验证码是否有效
        verified_code = await verification_code_crud.verify(
            db,
            user_id=user_id,
            code=code,
            code_type="email_verification"
        )
        
        if not verified_code:
            return False
        
        # 2) 标记用户邮箱已验证
        user = await user_crud.verify_email(db, user_id)
        
        if user:
            # 3) 发送欢迎邮件（非关键流程）
            await email_service.send_email(
                subject="Welcome!",
                recipient=user.email,
                template="welcome",
                username=user.username
            )
            return True
        
        return False
    
    @staticmethod
    async def login_user(
        db: AsyncSession,
        username: str,
        password: str,
        device_name: Optional[str] = None,
        device_type: Optional[str] = None,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None
    ) -> Optional[Token]:
        """用户登录：校验账号、状态、邮箱验证并签发令牌
        
        Args:
            db: 数据库会话
            username: 用户名或邮箱
            password: 密码
            device_name: 设备名称
            device_type: 设备类型
            ip_address: IP地址
            user_agent: 用户代理
            
        Returns:
            Token对象，认证失败时返回None
        """
        # 1) 校验用户名/邮箱与密码
        user = await user_crud.authenticate(db, username, password)
        if not user:
            return None
        
        # 2) 账号是否启用
        if not user.is_active:
            return None
        
        # 3) 邮箱是否已验证
        if not user.is_verified:
            return None
        
        # 4) 更新最近登录时间
        user.last_login_at = datetime.utcnow()
        await db.commit()
        
        # 5) 创建 access token
        access_token = AuthService.create_access_token(
            data={"sub": user.username, "user_id": user.id}
        )
        
        # 6) 创建 refresh token
        refresh_token = AuthService.create_refresh_token(
            data={"sub": user.username, "user_id": user.id}
        )
        
        # 7) 将 refresh token 持久化，便于多端管理与撤销
        expires_at = datetime.utcnow() + timedelta(seconds=settings.jwt.JWT_REFRESH_TOKEN_EXPIRATION)
        await refresh_token_crud.create(
            db,
            user_id=user.id,
            token=refresh_token,
            expires_at=expires_at,
            device_name=device_name,
            device_type=device_type,
            ip_address=ip_address,
            user_agent=user_agent
        )
        
        return Token(
            access_token=access_token,
            refresh_token=refresh_token,
            token_type="bearer"
        )
    
    @staticmethod
    async def refresh_access_token(db: AsyncSession, refresh_token: str) -> Optional[str]:
        """使用 refresh token 换取新的 access token
        
        Args:
            db: 数据库会话
            refresh_token: 刷新令牌
            
        Returns:
            新的访问令牌，刷新失败时返回None
        """
        # 1) 校验 refresh token 是否存在且有效
        db_token = await refresh_token_crud.get_by_token(db, refresh_token)
        
        if not db_token or not db_token.is_valid():
            return None
        
        # 2) 记录本次 refresh 使用时间
        await refresh_token_crud.update_last_used(db, db_token.id)
        
        # 3) 获取用户并校验状态
        user = await user_crud.get_by_id(db, db_token.user_id)
        if not user or not user.is_active:
            return None
        
        # 4) 签发新的 access token
        access_token = AuthService.create_access_token(
            data={"sub": user.username, "user_id": user.id}
        )
        
        return access_token
    
    @staticmethod
    async def request_password_reset(db: AsyncSession, email: str) -> bool:
        """发起找回密码流程（发送重置验证码）
        
        Args:
            db: 数据库会话
            email: 用户邮箱
            
        Returns:
            是否成功发送重置邮件
        """
        # 1) 查找用户（为避免枚举，用户不存在也返回 True）
        user = await user_crud.get_by_email(db, email)
        if not user:
            # 出于安全考虑，即使用户不存在也返回True
            return True
        
        # 2) 生成重置验证码
        code = await verification_code_crud.create(
            db,
            user_id=user.id,
            code_type="password_reset",
            expiration_minutes=60
        )
        
        # 3) 发送密码重置邮件
        await email_service.send_email(
            subject="Password Reset",
            recipient=user.email,
            template="password_reset",
            username=user.username,
            code=code.code
        )
        
        return True
    
    @staticmethod
    async def reset_password(db: AsyncSession, email: str, code: str, new_password: str) -> bool:
        """验证验证码并重置密码
        
        Args:
            db: 数据库会话
            email: 用户邮箱
            code: 验证码
            new_password: 新密码
            
        Returns:
            是否成功重置密码
        """
        # 1) 查找用户
        user = await user_crud.get_by_email(db, email)
        if not user:
            return False
        
        # 2) 校验验证码有效性
        verified_code = await verification_code_crud.verify(
            db,
            user_id=user.id,
            code=code,
            code_type="password_reset"
        )
        
        if not verified_code:
            return False
        
        # 3) 更新密码
        await user_crud.change_password(db, user.id, new_password)
        
        # 4) 使所有 refresh token 失效，强制重新登录
        await refresh_token_crud.revoke_user_tokens(db, user.id)
        
        return True
    
    @staticmethod
    async def logout_user(db: AsyncSession, refresh_token: str) -> bool:
        """单设备登出：撤销指定 refresh token
        
        Args:
            db: 数据库会话
            refresh_token: 刷新令牌
            
        Returns:
            是否成功登出
        """
        return await refresh_token_crud.revoke(db, refresh_token)
    
    @staticmethod
    async def logout_all_devices(db: AsyncSession, user_id: int) -> int:
        """全设备登出：撤销用户所有 refresh token
        
        Args:
            db: 数据库会话
            user_id: 用户ID
            
        Returns:
            撤销的令牌数量
        """
        return await refresh_token_crud.revoke_user_tokens(db, user_id)


# 全局服务实例
auth_service = AuthService()

