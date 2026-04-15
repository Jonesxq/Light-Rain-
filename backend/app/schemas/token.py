"""令牌数据验证模型模块 - 刷新令牌和验证码的请求/响应模型"""
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field, ConfigDict


# ========== 刷新令牌模型 ==========

class RefreshTokenBase(BaseModel):
    """刷新令牌基础模型 - 包含设备信息"""
    # 设备名称（可选）
    device_name: Optional[str] = Field(None, max_length=200)
    # 设备类型（可选，例如 web / mobile）
    device_type: Optional[str] = Field(None, max_length=50)


class RefreshTokenCreate(RefreshTokenBase):
    """刷新令牌创建模型 - 用于创建新的刷新令牌"""
    # 关联用户 ID
    user_id: int
    # 刷新令牌字符串
    token: str
    # 过期时间
    expires_at: datetime
    # IP 地址（可选）
    ip_address: Optional[str] = None
    # User-Agent（可选）
    user_agent: Optional[str] = None


class RefreshTokenResponse(RefreshTokenBase):
    """刷新令牌响应模型 - 返回刷新令牌的详细信息"""
    # 令牌 ID
    id: int
    # 关联用户 ID
    user_id: int
    # 过期时间
    expires_at: datetime
    # 是否已撤销
    is_revoked: bool
    # 创建时间
    created_at: datetime
    # 最后使用时间（可选）
    last_used_at: Optional[datetime] = None
    # IP 地址（可选）
    ip_address: Optional[str] = None
    
    model_config = ConfigDict(from_attributes=True)


class RefreshTokenRequest(BaseModel):
    """刷新令牌请求模型 - 用于请求新的访问令牌"""
    # 刷新令牌字符串
    refresh_token: str = Field(..., description="用于刷新访问令牌的刷新令牌")
    
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "refresh_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."
            }
        }
    )


class RefreshTokenRevoke(BaseModel):
    """刷新令牌撤销请求模型 - 用于撤销刷新令牌"""
    # 要撤销的令牌（可选）
    token: Optional[str] = Field(None, description="要撤销的刷新令牌，如果为空则撤销当前会话的令牌")


# ========== 验证码模型 ==========

class VerificationCodeBase(BaseModel):
    """验证码基础模型 - 包含验证码类型"""
    # 验证码类型（email_verification / password_reset）
    code_type: str = Field(..., description="验证码类型，如邮箱验证或密码重置")


class VerificationCodeCreate(VerificationCodeBase):
    """验证码创建模型 - 用于创建新的验证码"""
    # 关联用户 ID
    user_id: int
    # 验证码内容
    code: str
    # 过期时间
    expires_at: datetime
    # 最大尝试次数
    max_attempts: int = 5


class VerificationCodeResponse(VerificationCodeBase):
    """验证码响应模型 - 返回验证码的详细信息"""
    # 验证码 ID
    id: int
    # 关联用户 ID
    user_id: int
    # 过期时间
    expires_at: datetime
    # 是否已使用
    is_used: bool
    # 已尝试次数
    attempts: int
    # 最大尝试次数
    max_attempts: int
    # 创建时间
    created_at: datetime
    
    model_config = ConfigDict(from_attributes=True)


class VerificationCodeVerify(BaseModel):
    """验证码验证请求模型 - 用于验证用户输入的验证码"""
    # 用户输入的验证码
    code: str = Field(..., min_length=4, max_length=10)
    # 验证码类型
    code_type: str = Field(..., description="验证码类型，如邮箱验证或密码重置")
    
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "code": "123456",
                "code_type": "email_verification"
            }
        }
    )
