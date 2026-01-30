"""令牌相关的 Pydantic 模型定义（完整 JWT 认证）"""

from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field, ConfigDict

# ========== Refresh Token Schemas ==========

class RefreshTokenBase(BaseModel):
    """刷新令牌基础结构"""
    # 设备名称（可选）
    device_name: Optional[str] = Field(None, max_length=200)
    # 设备类型（可选，例如 web / mobile）
    device_type: Optional[str] = Field(None, max_length=50)


class RefreshTokenCreate(RefreshTokenBase):
    """创建刷新令牌的参数"""
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
    """刷新令牌响应结构"""
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
    """刷新访问令牌的请求体"""
    # 刷新令牌字符串
    refresh_token: str = Field(..., description="Generate token schemas (app/schemas/token.py)")
    
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "refresh_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."
            }
        }
    )


class RefreshTokenRevoke(BaseModel):
    """撤销刷新令牌的请求体"""
    # 要撤销的令牌（可选）
    token: Optional[str] = Field(None, description="Generate token schemas (app/schemas/token.py)")


# ========== Verification Code Schemas ==========

class VerificationCodeBase(BaseModel):
    """验证码基础结构"""
    # 验证码类型（email_verification / password_reset）
    code_type: str = Field(..., description="Generate token schemas (app/schemas/token.py)")


class VerificationCodeCreate(VerificationCodeBase):
    """创建验证码的参数"""
    # 关联用户 ID
    user_id: int
    # 验证码内容
    code: str
    # 过期时间
    expires_at: datetime
    # 最大尝试次数
    max_attempts: int = 5


class VerificationCodeResponse(VerificationCodeBase):
    """验证码响应结构"""
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
    """验证码校验请求体"""
    # 用户输入的验证码
    code: str = Field(..., min_length=4, max_length=10)
    # 验证码类型
    code_type: str = Field(..., description="Generate token schemas (app/schemas/token.py)")
    
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "code": "123456",
                "code_type": "email_verification"
            }
        }
    )

