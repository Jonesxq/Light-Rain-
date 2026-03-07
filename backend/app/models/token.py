"""令牌数据模型模块 - 管理刷新令牌和验证码"""
from datetime import datetime
from typing import Optional
from sqlalchemy import Column, ForeignKey
from sqlmodel import Field, SQLModel, Relationship


class RefreshToken(SQLModel, table=True):
    """刷新令牌数据模型 - 管理用户的登录刷新令牌
    
    用于实现无感知的用户登录状态保持，支持设备信息记录
    """
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
        """配置类 - Pydantic模型配置"""
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
        """检查刷新令牌是否有效
        
        检查令牌是否未被撤销且未过期
        
        Returns:
            bool: 令牌有效返回True，否则返回False
        """
        if self.is_revoked:
            return False
        return datetime.utcnow() < self.expires_at
    
    def revoke(self) -> None:
        """撤销刷新令牌
        
        标记令牌为已撤销并记录撤销时间
        """
        self.is_revoked = True
        self.revoked_at = datetime.utcnow()


class VerificationCode(SQLModel, table=True):
    """验证码数据模型 - 管理邮箱验证、密码重置等验证码
    
    支持验证次数限制，防止暴力破解
    """
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
        """配置类 - Pydantic模型配置"""
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
        """检查验证码是否有效
        
        检查验证码是否未使用、未超次数且未过期
        
        Returns:
            bool: 验证码有效返回True，否则返回False
        """
        if self.is_used:
            return False
        if self.attempts >= self.max_attempts:
            return False
        return datetime.utcnow() < self.expires_at
    
    def increment_attempts(self) -> None:
        """增加验证尝试次数
        
        用于防止暴力破解
        """
        self.attempts += 1
    
    def mark_as_used(self) -> None:
        """标记验证码为已使用
        
        验证成功后调用此方法
        """
        self.is_used = True
        self.used_at = datetime.utcnow()
