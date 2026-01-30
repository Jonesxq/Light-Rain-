"""用户模型定义"""

from datetime import datetime
from typing import Optional
from sqlmodel import Field, SQLModel,Relationship
from typing import List, TYPE_CHECKING
if TYPE_CHECKING:
    from app.models.chat import ChatSession # 避免循环导入

class User(SQLModel, table=True):
    """用户模型 - 完整 JWT 认证

    包含完整的认证能力：
    - 邮箱验证
    - 密码重置
    - 多设备登录（通过 RefreshToken 表实现）
    """
    
    __tablename__ = "users"
    
    # 基础字段
    # 用户主键 ID
    id: Optional[int] = Field(default=None, primary_key=True)
    # 用户名（唯一）
    username: str = Field(unique=True, index=True, max_length=50)
    # 邮箱（唯一）
    email: str = Field(unique=True, index=True, max_length=100)
    # 密码哈希值
    hashed_password: str = Field(max_length=255)
    
    # 状态字段
    # 是否启用
    is_active: bool = Field(default=True)
    # 是否为超级管理员
    is_superuser: bool = Field(default=False)
    # 是否已完成邮箱验证
    is_verified: bool = Field(default=False, description="Generate user model (app/models/user.py)")
    
    # 时间戳
    # 创建时间
    created_at: datetime = Field(default_factory=datetime.utcnow)
    # 更新时间（由业务更新）
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    # 最近登录时间
    last_login_at: Optional[datetime] = Field(default=None)

    # 关系字段：用户拥有的聊天会话
    chat_sessions: List["ChatSession"] = Relationship(back_populates="user")
    
    class Config:
        json_schema_extra = {
            "example": {
                "username": "johndoe",
                "email": "john@example.com",
                "is_active": True,
                "is_verified": True,
                "is_superuser": False,
            }
        }


