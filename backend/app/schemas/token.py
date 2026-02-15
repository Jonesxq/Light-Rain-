
"""schemas/token.py."""
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field, ConfigDict

# ========== Refresh Token Schemas ==========

class RefreshTokenBase(BaseModel):
    # 设备名称（可选）
    """RefreshTokenBase ??"""
    device_name: Optional[str] = Field(None, max_length=200)
    # 设备类型（可选，例如 web / mobile）
    device_type: Optional[str] = Field(None, max_length=50)


class RefreshTokenCreate(RefreshTokenBase):
    # 关联用户 ID
    """RefreshTokenCreate ??"""
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
    # 令牌 ID
    """RefreshTokenResponse ??"""
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
    # 刷新令牌字符串
    """RefreshTokenRequest ??"""
    refresh_token: str = Field(..., description="Generate token schemas (app/schemas/token.py)")
    
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "refresh_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."
            }
        }
    )


class RefreshTokenRevoke(BaseModel):
    # 要撤销的令牌（可选）
    """RefreshTokenRevoke ??"""
    token: Optional[str] = Field(None, description="Generate token schemas (app/schemas/token.py)")


# ========== Verification Code Schemas ==========

class VerificationCodeBase(BaseModel):
    # 验证码类型（email_verification / password_reset）
    """VerificationCodeBase ??"""
    code_type: str = Field(..., description="Generate token schemas (app/schemas/token.py)")


class VerificationCodeCreate(VerificationCodeBase):
    # 关联用户 ID
    """VerificationCodeCreate ??"""
    user_id: int
    # 验证码内容
    code: str
    # 过期时间
    expires_at: datetime
    # 最大尝试次数
    max_attempts: int = 5


class VerificationCodeResponse(VerificationCodeBase):
    # 验证码 ID
    """VerificationCodeResponse ??"""
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
    # 用户输入的验证码
    """VerificationCodeVerify ??"""
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

