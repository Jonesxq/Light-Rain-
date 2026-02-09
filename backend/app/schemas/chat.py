"""聊天相关的 Pydantic 模型定义"""
from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel, ConfigDict
from app.models.chat import ChatRole


# ========== Message Schemas ==========

class ChatMessageBase(BaseModel):
    """消息基础结构"""
    # 消息角色（system / user / assistant）
    role: ChatRole
    # 消息正文内容
    content: str


class ChatMessageCreate(ChatMessageBase):
    """创建消息时的参数"""
    pass


class ChatMessageResponse(ChatMessageBase):
    """返回给前端的消息格式"""
    # 消息 ID
    id: int
    # 创建时间
    created_at: datetime
    # 使用的模型名称（可选）
    model_name: Optional[str] = None
    # 知识库引用来源（可选）
    sources: Optional[List["KnowledgeSource"]] = None

    model_config = ConfigDict(from_attributes=True)


class KnowledgeSource(BaseModel):
    """知识库引用来源信息"""
    # 文档 ID
    doc_id: Optional[int] = None
    # 文件名
    file_name: Optional[str] = None
    # 文件类型
    file_type: Optional[str] = None
    # PDF 页码（可选）
    pages: Optional[List[int]] = None
    # PPT 幻灯片页码（可选）
    slides: Optional[List[int]] = None
    # DOCX 段落序号（可选）
    paragraphs: Optional[List[int]] = None
    # 表格序号（可选）
    tables: Optional[List[int]] = None
    # Markdown 标题路径（可选）
    md_headings: Optional[str] = None
    # 分块序号（可选）
    chunk_index: Optional[int] = None


class KnowledgeChatResponse(ChatMessageResponse):
    """知识库问答返回格式（包含引用来源）"""
    sources: Optional[List[KnowledgeSource]] = None


# ========== Session Schemas ==========

class ChatSessionCreate(BaseModel):
    """创建会话的参数"""
    # 会话标题（可选）
    title: Optional[str] = "New Chat"


class ChatSessionUpdate(BaseModel):
    """更新会话的参数"""
    # 新的会话标题
    title: str


class ChatSessionResponse(BaseModel):
    """返回给前端的会话信息"""
    # 会话 ID
    id: int
    # 会话标题
    title: str
    # 创建时间
    created_at: datetime
    # 更新时间
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


# ========== API Request Schemas ==========

class ChatRequest(BaseModel):
    """用户发送聊天的请求体"""
    # 用户输入的消息
    message: str
    # 使用的模型名称（默认值可按需调整）
    model: Optional[str] = None



class KnowledgeChatRequest(BaseModel):
    """知识库问答请求体"""
    # 用户提出的问题
    message: str
    # 使用哪个知识库
    kb_id: int
    # 关联已有会话（可选）
    session_id: Optional[int] = None
    # 使用的模型名称
    model: Optional[str] = None
