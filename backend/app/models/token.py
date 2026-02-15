
"""models/token.py."""
from datetime import datetime
from typing import Optional
from sqlalchemy import Column, ForeignKey
from sqlmodel import Field, SQLModel, Relationship

class RefreshToken(SQLModel, table=True):
    
    """RefreshToken ??"""
    __tablename__ = "refresh_tokens"
    
    # 主键 ID
    id: Optional[int] = Field(default=None, primary_key=True)
    
    # 关联用户 ID
    user_id: int = Field(
        sa_column=Column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    )
    
    # 令牌信息
    token: str = Field(unique=True, index=True, max_length=500)
    # 过期时间
    expires_at: datetime = Field(index=True)
    
    # 设备信息（可选）
    # 设备名称，例如 iPhone 13
    device_name: Optional[str] = Field(default=None, max_length=100)
    # 设备类型，例如 web / mobile / desktop
    device_type: Optional[str] = Field(default=None, max_length=50)  # web, mobile, desktop
    # IP 地址（IPv6 最大长度 45）
    ip_address: Optional[str] = Field(default=None, max_length=45)  # IPv6 max length 45 characters
    # User-Agent 信息
    user_agent: Optional[str] = Field(default=None, max_length=500)
    
    # 状态字段
    # 是否被撤销
    is_revoked: bool = Field(default=False, index=True)
    # 撤销时间
    revoked_at: Optional[datetime] = Field(default=None)
    
    # 时间戳
    # 创建时间
    created_at: datetime = Field(default_factory=datetime.utcnow)
    # 最后使用时间
    last_used_at: Optional[datetime] = Field(default=None)
    
    class Config:
        """Config ??"""
        json_schema_extra = {
            "example": {
                "user_id": 1,
                "token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
                "device_name": "iPhone 13",
                "device_type": "mobile",
                "is_revoked": False,
            }
        }
    
    def is_valid(self) -> bool:
        """is_valid ???"""
        if self.is_revoked:
            return False
        return datetime.utcnow() < self.expires_at
    
    def revoke(self) -> None:
        """revoke ???"""
        self.is_revoked = True
        self.revoked_at = datetime.utcnow()


class VerificationCode(SQLModel, table=True):
    
    """VerificationCode ??"""
    __tablename__ = "verification_codes"
    
    # 主键 ID
    id: Optional[int] = Field(default=None, primary_key=True)
    
    # 关联用户 ID
    user_id: int = Field(
        sa_column=Column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    )
    
    # 验证码信息
    # 验证码内容
    code: str = Field(max_length=10, index=True)
    # 验证码类型（例如邮箱验证、密码重置）
    code_type: str = Field(max_length=20, index=True)  # email_verification, password_reset
    # 过期时间
    expires_at: datetime = Field(index=True)
    
    # 使用状态
    # 是否已使用
    is_used: bool = Field(default=False, index=True)
    # 使用时间
    used_at: Optional[datetime] = Field(default=None)
    # 已尝试次数
    attempts: int = Field(default=0)  # Attempt count
    # 最大尝试次数
    max_attempts: int = Field(default=5)  # Maximum attempts
    
    # 时间戳
    created_at: datetime = Field(default_factory=datetime.utcnow)
    
    class Config:
        """Config ??"""
        json_schema_extra = {
            "example": {
                "user_id": 1,
                "code": "123456",
                "code_type": "email_verification",
                "is_used": False,
                "attempts": 0,
            }
        }
    
    def is_valid(self) -> bool:
        """is_valid ???"""
        if self.is_used:
            return False
        if self.attempts >= self.max_attempts:
            return False
        return datetime.utcnow() < self.expires_at
    
    def increment_attempts(self) -> None:
        """increment_attempts ???"""
        self.attempts += 1
    
    def mark_as_used(self) -> None:
        """mark_as_used ???"""
        self.is_used = True
        self.used_at = datetime.utcnow()

