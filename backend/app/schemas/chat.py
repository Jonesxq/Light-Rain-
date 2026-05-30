"""聊天数据验证模型模块"""
from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel, ConfigDict, Field, field_validator
from app.models.chat import ChatRole


# ========== 消息模型 ==========

class ChatMessageBase(BaseModel):
    """聊天消息基础模型"""
    # 消息角色（system / user / assistant）
    role: ChatRole
    # 消息正文内容
    content: str


class ChatMessageCreate(ChatMessageBase):
    """聊天消息创建模型"""
    pass


class ChatMessageResponse(ChatMessageBase):
    """聊天消息响应模型"""
    # 消息 ID
    id: int
    # 创建时间
    created_at: datetime
    # 是否收藏
    is_favorite: bool = False
    # 编辑时间
    edited_at: Optional[datetime] = None
    # 使用的模型名称（可选）
    model_name: Optional[str] = None
    # 知识库引用来源（可选）
    sources: Optional[List["KnowledgeSource"]] = None
    # 免责声明（可选）
    disclaimers: List["ChatDisclaimer"] = []
    # 风险标签（可选）
    risk_tags: Optional[List[str]] = None

    model_config = ConfigDict(from_attributes=True)


class KnowledgeSource(BaseModel):
    """知识库来源模型"""
    # 文档 ID
    doc_id: Optional[int] = None
    # Web 标题
    title: Optional[str] = None
    # 网页链接
    url: Optional[str] = None
    # Web 摘要
    snippet: Optional[str] = None
    # 来源类型（web / kb）
    source_type: Optional[str] = None
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
    # 分块主键（可选，稳定映射原文）
    chunk_id: Optional[int] = None
    # 分块序号（可选）
    chunk_index: Optional[int] = None


class ChatDisclaimer(BaseModel):
    """聊天免责声明模型"""
    code: str
    title: str
    body: str
    severity: str = "warning"


class KnowledgeChatResponse(ChatMessageResponse):
    """知识库聊天响应模型"""
    sources: Optional[List[KnowledgeSource]] = None


# ========== 会话模型 ==========

class ChatSessionCreate(BaseModel):
    """聊天会话创建模型"""
    # 会话标题（可选）
    title: Optional[str] = "New Chat"


class ChatSessionUpdate(BaseModel):
    """聊天会话更新模型"""
    # 新的会话标题
    title: Optional[str] = None
    is_pinned: Optional[bool] = None
    is_archived: Optional[bool] = None
    tags: Optional[List[str]] = None


class ChatSessionResponse(BaseModel):
    """聊天会话响应模型"""
    # 会话 ID
    id: int
    # 会话标题
    title: str
    # 是否置顶
    is_pinned: bool = False
    # 是否归档
    is_archived: bool = False
    # 标签
    tags: List[str] = Field(default_factory=list)
    # 创建时间
    created_at: datetime
    # 更新时间
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)

    @field_validator("tags", mode="before")
    @classmethod
    def _coerce_tags(cls, v):
        if v is None:
            return []
        return list(v)

# ========== API请求模型 ==========

class ChatRequest(BaseModel):
    """聊天请求模型"""
    # 用户输入的消息
    message: str
    # 深度思考（边想边搜）
    deep_search: bool = False
    # 深度思考（推理）
    deep_think: bool = False


class ChatSuggestionRequest(BaseModel):
    """聊天建议请求模型"""
    limit: int = Field(default=3)
    model: Optional[str] = None


class ChatSuggestionResponse(BaseModel):
    """聊天建议响应模型"""
    session_id: int
    suggestions: List[str]


class ChatRegenerateRequest(BaseModel):
    """聊天重新生成请求模型"""
    deep_search: bool = False
    deep_think: bool = False


class FavoriteUpdateRequest(BaseModel):
    """收藏更新请求模型"""
    is_favorite: bool



class KnowledgeChatRequest(BaseModel):
    """知识库聊天请求模型"""
    # 用户提出的问题
    message: str
    # 使用哪个知识库
    kb_id: int
    # 关联已有会话（可选）
    session_id: Optional[int] = None
    # 使用的模型名称
    model: Optional[str] = None


class ChatAttachmentResponse(BaseModel):
    """聊天附件响应模型"""
    id: int
    file_name: str
    file_type: str
    file_size: int
    preview: str = ""
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ChatPromptSnapshotResponse(BaseModel):
    """聊天提示词快照响应模型"""
    id: int
    message_id: int
    user_id: int
    session_id: int
    mode: str
    payload: dict
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)
