"""认证路由模块 - 提供用户注册、登录、邮箱验证、密码重置等认证相关API"""
from fastapi import APIRouter, Depends, HTTPException, status, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import get_current_user
from app.models.user import User
from app.schemas.user import (
    UserCreate,
    UserResponse,
    UserLogin,
    Token,
    EmailVerificationRequest,
    ResendVerificationRequest,
    PasswordResetRequest,
    PasswordResetConfirm,
    PasswordChange,
)
from app.schemas.token import RefreshTokenRequest, RefreshTokenResponse
from app.services.auth import auth_service
from app.crud.user import user_crud
from app.crud.token import refresh_token_crud

router = APIRouter(prefix="/auth", tags=["Authentication"])


# ========== 注册与登录 ==========

@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def register(
    user_data: UserCreate,
    db: AsyncSession = Depends(get_db)
):
    """用户注册接口
    
    创建新用户账户并发送邮箱验证邮件
    
    Args:
        user_data: 用户注册信息
        db: 数据库会话
        
    Returns:
        UserResponse: 新创建的用户信息
        
    Raises:
        HTTPException: 用户名或邮箱已存在时返回400错误
    """
    try:
        user = await auth_service.register_user(db, user_data, send_verification=True)
        return user
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


@router.post("/login", response_model=Token)
async def login(
    user_login: UserLogin,
    request: Request,
    db: AsyncSession = Depends(get_db)
):
    """用户登录接口
    
    支持使用用户名或邮箱登录，成功后返回访问令牌和刷新令牌
    
    Args:
        user_login: 登录凭据
        request: HTTP请求对象，用于获取设备信息
        db: 数据库会话
        
    Returns:
        Token: 访问令牌和刷新令牌
        
    Raises:
        HTTPException: 凭据错误或邮箱未验证时返回401错误
    """
    # 获取设备信息
    user_agent = request.headers.get("User-Agent", "Unknown")
    ip_address = request.client.host if request.client else None
    
    # 优先使用邮箱，其次使用用户名
    login_identifier = user_login.email or user_login.username
    
    token = await auth_service.login_user(
        db,
        login_identifier,
        user_login.password,
        device_name=user_agent[:100] if user_agent else None,
        device_type="web",
        ip_address=ip_address,
        user_agent=user_agent
    )
    
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password, or email not verified",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    return token


@router.post("/logout")
async def logout(
    refresh_token_request: RefreshTokenRequest,
    db: AsyncSession = Depends(get_db)
):
    """用户登出接口
    
    撤销指定的刷新令牌
    
    Args:
        refresh_token_request: 刷新令牌
        db: 数据库会话
        
    Returns:
        dict: 登出成功消息
        
    Raises:
        HTTPException: 令牌无效时返回400错误
    """
    success = await auth_service.logout_user(db, refresh_token_request.refresh_token)
    
    if not success:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid refresh token"
        )
    
    return {"message": "Successfully logged out"}


@router.post("/logout-all")
async def logout_all(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """撤销所有设备的登录
    
    撤销当前用户的所有刷新令牌，强制所有设备重新登录
    
    Args:
        current_user: 当前登录用户
        db: 数据库会话
        
    Returns:
        dict: 登出成功消息和撤销的设备数量
    """
    count = await auth_service.logout_all_devices(db, current_user.id)
    return {"message": f"Successfully logged out from {count} devices"}


# ========== 令牌刷新 ==========

@router.post("/refresh", response_model=dict)
async def refresh_token(
    refresh_token_request: RefreshTokenRequest,
    db: AsyncSession = Depends(get_db)
):
    """刷新访问令牌接口
    
    使用有效的刷新令牌获取新的访问令牌
    
    Args:
        refresh_token_request: 刷新令牌
        db: 数据库会话
        
    Returns:
        dict: 新的访问令牌
        
    Raises:
        HTTPException: 令牌无效或过期时返回401错误
    """
    access_token = await auth_service.refresh_access_token(db, refresh_token_request.refresh_token)
    
    if not access_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired refresh token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    return {"access_token": access_token, "token_type": "bearer"}


# ========== 邮箱验证 ==========

@router.post("/verify-email")
async def verify_email(
    verification: EmailVerificationRequest,
    db: AsyncSession = Depends(get_db)
):
    """验证用户邮箱
    
    使用邮箱和验证码完成邮箱验证
    
    Args:
        verification: 邮箱验证请求
        db: 数据库会话
        
    Returns:
        dict: 验证成功消息
        
    Raises:
        HTTPException: 用户不存在或验证码无效时返回相应错误
    """
    # 查询用户
    user = await user_crud.get_by_email(db, verification.email)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )
    
    # 校验邮箱验证码
    success = await auth_service.verify_email(db, user.id, verification.code)
    
    if not success:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired verification code"
        )
    
    return {"message": "Email verified successfully"}


@router.post("/resend-verification")
async def resend_verification(
    request: ResendVerificationRequest,
    db: AsyncSession = Depends(get_db)
):
    """重新发送邮箱验证邮件
    
    向指定邮箱重新发送验证码（出于安全考虑，即使邮箱不存在也返回成功）
    
    Args:
        request: 重新发送验证请求
        db: 数据库会话
        
    Returns:
        dict: 发送成功消息
        
    Raises:
        HTTPException: 邮箱已验证时返回400错误
    """
    # 查询用户
    user = await user_crud.get_by_email(db, request.email)
    if not user:
        # 出于安全考虑，即使用户不存在也返回成功提示
        return {"message": "If the email exists, a verification code has been sent"}
    
    # 检查是否已完成验证
    if user.is_verified:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already verified"
        )
    
    # 发送验证邮件
    await auth_service.send_verification_email(db, user)
    
    return {"message": "Verification email sent"}


# ========== 找回密码 ==========

@router.post("/forgot-password")
async def forgot_password(
    request: PasswordResetRequest,
    db: AsyncSession = Depends(get_db)
):
    """请求密码重置
    
    向指定邮箱发送密码重置验证码（出于安全考虑，即使邮箱不存在也返回成功）
    
    Args:
        request: 密码重置请求
        db: 数据库会话
        
    Returns:
        dict: 发送成功消息
    """
    await auth_service.request_password_reset(db, request.email)
    
    # 出于安全考虑，始终返回成功提示
    return {"message": "If the email exists, a password reset code has been sent"}


@router.post("/reset-password")
async def reset_password(
    reset_data: PasswordResetConfirm,
    db: AsyncSession = Depends(get_db)
):
    """确认密码重置
    
    使用验证码重置用户密码
    
    Args:
        reset_data: 密码重置确认信息
        db: 数据库会话
        
    Returns:
        dict: 重置成功消息
        
    Raises:
        HTTPException: 验证码无效或过期时返回400错误
    """
    success = await auth_service.reset_password(
        db,
        reset_data.email,
        reset_data.code,
        reset_data.new_password
    )
    
    if not success:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired reset code"
        )
    
    return {"message": "Password reset successfully"}


@router.post("/change-password")
async def change_password(
    password_data: PasswordChange,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """修改用户密码
    
    验证旧密码后设置新密码，并撤销所有刷新令牌
    
    Args:
        password_data: 密码修改信息
        current_user: 当前登录用户
        db: 数据库会话
        
    Returns:
        dict: 修改成功消息
        
    Raises:
        HTTPException: 旧密码错误时返回400错误
    """
    # 校验旧密码
    user = await user_crud.authenticate(db, current_user.username, password_data.old_password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Incorrect old password"
        )
    
    # 修改密码
    await user_crud.change_password(db, current_user.id, password_data.new_password)
    
    # 撤销全部刷新令牌（强制重新登录）
    await refresh_token_crud.revoke_user_tokens(db, current_user.id)
    
    return {"message": "Password changed successfully. Please login again."}


# ========== 设备管理 ==========

@router.get("/devices", response_model=list[RefreshTokenResponse])
async def list_devices(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """获取当前用户的登录设备列表
    
    列出所有有效的刷新令牌及其设备信息
    
    Args:
        current_user: 当前登录用户
        db: 数据库会话
        
    Returns:
        list[RefreshTokenResponse]: 设备列表
    """
    tokens = await refresh_token_crud.get_user_tokens(db, current_user.id, include_revoked=False)
    return tokens
