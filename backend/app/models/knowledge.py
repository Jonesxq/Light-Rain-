"""知识库数据模型模块"""
from datetime import datetime
from typing import Optional, List, TYPE_CHECKING
from sqlmodel import Field, SQLModel, Relationship, Column, Text
from sqlalchemy import JSON
from enum import Enum

if TYPE_CHECKING:
    from app.models.user import User


class DocStatus(str, Enum):
    """文档处理状态枚举"""
    UPLOADING = "uploading"
    PROCESSING = "processing"  # 正在解析/嵌入
    COMPLETED = "completed"  # 处理完成
    FAILED = "failed"  # 处理失败


class KnowledgeBase(SQLModel, table=True):
    """知识库数据模型"""
    __tablename__ = "knowledge_bases"

    # 主键
    id: Optional[int] = Field(default=None, primary_key=True)
    # 知识库名称
    name: str = Field(max_length=100, index=True)
    # 知识库描述
    description: Optional[str] = Field(default=None, max_length=500)

    # 归属用户
    user_id: int = Field(foreign_key="users.id", index=True)

    # 创建/更新时间
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    # 关系
    documents: List["Document"] = Relationship(back_populates="kb", sa_relationship_kwargs={"cascade": "all, delete"})


class Document(SQLModel, table=True):
    """文档数据模型"""
    __tablename__ = "kb_documents"

    # 主键
    id: Optional[int] = Field(default=None, primary_key=True)
    # 归属知识库
    kb_id: int = Field(foreign_key="knowledge_bases.id", index=True)

    # 文件基础信息
    file_name: str = Field(max_length=255)
    file_path: str = Field(max_length=512)  # 文件在服务器或OSS的存储路径
    file_type: str = Field(max_length=20)  # .pdf, .docx, .md 等
    file_size: int = Field(default=0)  # 字节数

    # 解析状态与错误信息
    status: DocStatus = Field(default=DocStatus.UPLOADING)
    error_msg: Optional[str] = Field(default=None)  # 如果失败记录原因

    # 分块数量
    chunk_count: int = Field(default=0)  # 切片总数

    # 创建时间
    created_at: datetime = Field(default_factory=datetime.utcnow)

    # 关系
    kb: KnowledgeBase = Relationship(back_populates="documents")
    chunks: List["DocumentChunk"] = Relationship(back_populates="document",
                                                 sa_relationship_kwargs={"cascade": "all, delete"})


class DocumentChunk(SQLModel, table=True):
    """文档块数据模型"""
    __tablename__ = "kb_doc_chunks"

    id: Optional[int] = Field(default=None, primary_key=True)
    doc_id: int = Field(foreign_key="kb_documents.id", index=True)
    # 摘要切片与原文切片的一对一映射键
    parent_id: str = Field(max_length=128, index=True)

    # 存储摘要文本（原文 chunk 仅保存在本地 sidecar 文件）
    content: str = Field(sa_column=Column(Text))

    # 在向量库中的唯一标识 (Milvus 的 Entity ID)
    vector_id: str = Field(max_length=64, index=True)

    # 切片在文档中的序号
    chunk_index: int = Field(default=0)
    # Token 数量（用于预算分析）
    token_count: int = Field(default=0)
    # 结构化元数据（页码/标题路径/分块信息/文档信息等）
    structured_meta: Optional[dict] = Field(default=None, sa_column=Column(JSON))

    # 关系
    document: Document = Relationship(back_populates="chunks")
