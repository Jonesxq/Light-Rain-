"""
Chat models definition
包括会话(Session)和消息(Message)的定义
"""

from datetime import datetime
from typing import Optional, List, TYPE_CHECKING # 引入 TYPE_CHECKING
from enum import Enum
from sqlmodel import Field, SQLModel, Relationship, Column, Text
from sqlalchemy import ForeignKey, JSON

# 移除顶部的直接导入，避免运行时循环导入错误
# from app.models.user import User  <-- 删掉这一行

# 仅在类型检查时导入 User，运行时不会执行，避免死循环
if TYPE_CHECKING:
    from app.models.user import User

class ChatRole(str, Enum):
    """消息角色枚举"""
    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"

class ChatSession(SQLModel, table=True):
    """
    聊天会话表 (Chat Session)
    对应界面左侧的会话列表
    """
    __tablename__ = "chat_sessions"

    id: Optional[int] = Field(default=None, primary_key=True)

    # 1. 外键字段：数据库里实际存的列
    user_id: int = Field(foreign_key="users.id", index=True)

    title: str = Field(default="New Chat", max_length=100)
    is_deleted: bool = Field(default=False, index=True)
    is_pinned: bool = Field(default=False)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow, index=True)

    # 2. 关系字段：SQLModel ORM 层面使用的对象
    # 加上这一行，你刚才问的 User 导入就有用了
    # 使用字符串 "User" 是为了配合 TYPE_CHECKING 延迟解析
    user: Optional["User"] = Relationship(back_populates="chat_sessions")

    # 与消息的一对多关系
    messages: List["ChatMessage"] = Relationship(back_populates="session", sa_relationship_kwargs={"cascade": "all, delete"})

    class Config:
        json_schema_extra = {
            "example": {
                "user_id": 1,
                "title": "Python SQLModel Help",
                "is_pinned": False
            }
        }

class ChatMessage(SQLModel, table=True):
    """聊天消息表"""
    __tablename__ = "chat_messages"
    id: Optional[int] = Field(default=None, primary_key=True)
    # 所属会话
    session_id: int = Field(foreign_key="chat_sessions.id", index=True)
    # 关联知识库（可选，删除知识库时置空）
    kb_id: Optional[int] = Field(
        default=None,
        sa_column=Column(ForeignKey("knowledge_bases.id", ondelete="SET NULL"), nullable=True, index=True)
    )
    # 消息角色：用户/助手/系统
    role: ChatRole = Field(index=True)
    # 消息内容（长文本）
    content: str = Field(sa_column=Column(Text))
    # 使用的模型名称（可选）
    model_name: Optional[str] = Field(default=None, max_length=50)
    # 计费 token 数（可选）
    token_count: Optional[int] = Field(default=0)
    # 知识库引用来源（结构化元数据列表）
    sources: Optional[list[dict]] = Field(default=None, sa_column=Column(JSON))
    # 创建时间
    created_at: datetime = Field(default_factory=datetime.utcnow, index=True)


    # 关系
    session: ChatSession = Relationship(back_populates="messages")
