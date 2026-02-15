
"""schemas/user.py."""
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, EmailStr, Field, ConfigDict, model_validator

# ========== base Schema ==========

class UserBase(BaseModel):
    # 用户名（长度 3-50）
    """UserBase ??"""
    username: str = Field(..., min_length=3, max_length=50)
    # 邮箱
    email: EmailStr


class UserCreate(UserBase):
    # 明文密码（用于注册）
    """UserCreate ??"""
    password: str = Field(..., min_length=6, max_length=100)
    
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "username": "johndoe",
                "email": "john@example.com",
                "password": "strongpassword123"
            }
        }
    )


class UserUpdate(BaseModel):
    # 新用户名（可选）
    """UserUpdate ??"""
    username: Optional[str] = Field(None, min_length=3, max_length=50)
    # 新邮箱（可选）
    email: Optional[EmailStr] = None
    # 新密码（可选）
    password: Optional[str] = Field(None, min_length=6, max_length=100)
    # 是否启用（可选）
    is_active: Optional[bool] = None


class UserResponse(UserBase):
    # 用户 ID
    """UserResponse ??"""
    id: int
    # 是否启用
    is_active: bool
    # 是否完成邮箱验证
    is_verified: bool
    # 是否为超级管理员
    is_superuser: bool
    # 创建时间
    created_at: datetime
    # 更新时间
    updated_at: datetime
    # 最近登录时间（可选）
    last_login_at: Optional[datetime] = None
    
    model_config = ConfigDict(from_attributes=True)


# ========== authenticationrelated Schema ==========

class UserLogin(BaseModel):
    # 用户名（与邮箱二选一）
    """UserLogin ??"""
    username: Optional[str] = Field(None, description="Generate user schemas (app/schemas/user.py)")
    # 邮箱（与用户名二选一）
    email: Optional[EmailStr] = Field(None, description="Generate user schemas (app/schemas/user.py)")
    # 登录密码
    password: str = Field(..., min_length=6)
    
    @model_validator(mode='after')
    def check_username_or_email(self):
        """check_username_or_email ???"""
        if not self.username and not self.email:
            raise ValueError('Must provide username or email')
        return self
    
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "email": "user@example.com",
                "password": "strongpassword123"
            }
        }
    )


class Token(BaseModel):
    # 访问令牌
    """Token ??"""
    access_token: str
    # 刷新令牌（可选）
    refresh_token: Optional[str] = None
    # 令牌类型
    token_type: str = "bearer"
    
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
                "refresh_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
                "token_type": "bearer"
            }
        }
    )


class TokenData(BaseModel):
    # 用户名（可选）
    """TokenData ??"""
    username: Optional[str] = None
    # 用户 ID（可选）
    user_id: Optional[int] = None


class RefreshTokenRequest(BaseModel):
    # 刷新令牌字符串
    """RefreshTokenRequest ??"""
    refresh_token: str = Field(..., description="Generate user schemas (app/schemas/user.py)")


# ========== EmailValidaterelated Schema ==========

class EmailVerificationRequest(BaseModel):
    # 邮箱
    """EmailVerificationRequest ??"""
    email: EmailStr
    # 验证码
    code: str = Field(..., min_length=4, max_length=10)
    
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "email": "john@example.com",
                "code": "123456"
            }
        }
    )


class ResendVerificationRequest(BaseModel):
    # 邮箱
    """ResendVerificationRequest ??"""
    email: EmailStr


# ========== Passwordresetrelated Schema ==========

class PasswordResetRequest(BaseModel):
    # 邮箱
    """PasswordResetRequest ??"""
    email: EmailStr
    
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "email": "john@example.com"
            }
        }
    )


class PasswordResetConfirm(BaseModel):
    # 邮箱
    """PasswordResetConfirm ??"""
    email: EmailStr
    # 验证码
    code: str = Field(..., min_length=4, max_length=10)
    # 新密码
    new_password: str = Field(..., min_length=6, max_length=100)
    
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "email": "john@example.com",
                "code": "123456",
                "new_password": "newstrongpassword123"
            }
        }
    )


class PasswordChange(BaseModel):
    # 旧密码
    """PasswordChange ??"""
    old_password: str = Field(..., min_length=6)
    # 新密码
    new_password: str = Field(..., min_length=6, max_length=100)
    
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "old_password": "oldpassword123",
                "new_password": "newstrongpassword123"
            }
        }
    )

