"""知识库数据库操作模块 - 提供知识库、文档和文档分块的CRUD操作"""
from typing import List, Optional
from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select, desc, update
from app.models.knowledge import KnowledgeBase, Document, DocumentChunk, DocStatus
from app.models.chat import ChatMessage


class KnowledgeCRUD:
    """知识库CRUD操作类 - 管理知识库、文档和文档分块的数据库操作"""

    # ========== 知识库 (KnowledgeBase) 操作 ==========

    async def create_kb(self, db: AsyncSession, user_id: int, name: str, description: Optional[str] = None) -> KnowledgeBase:
        """创建新的知识库
        
        Args:
            db: 异步数据库会话
            user_id: 用户ID
            name: 知识库名称
            description: 知识库描述
            
        Returns:
            KnowledgeBase: 创建的知识库对象
        """
        kb = KnowledgeBase(user_id=user_id, name=name, description=description)
        db.add(kb)
        await db.commit()
        await db.refresh(kb)
        return kb

    async def get_user_kbs(self, db: AsyncSession, user_id: int) -> List[KnowledgeBase]:
        """获取用户的所有知识库
        
        Args:
            db: 异步数据库会话
            user_id: 用户ID
            
        Returns:
            List[KnowledgeBase]: 知识库列表，按创建时间倒序排列
        """
        statement = select(KnowledgeBase).where(KnowledgeBase.user_id == user_id).order_by(desc(KnowledgeBase.created_at))
        result = await db.execute(statement)
        return list(result.scalars().all())

    async def get_kb(self, db: AsyncSession, kb_id: int) -> Optional[KnowledgeBase]:
        """根据ID获取知识库
        
        Args:
            db: 异步数据库会话
            kb_id: 知识库ID
            
        Returns:
            Optional[KnowledgeBase]: 知识库对象，如果不存在则返回None
        """
        return await db.get(KnowledgeBase, kb_id)

    async def delete_kb(self, db: AsyncSession, kb_id: int) -> bool:
        """删除知识库
        
        会先解除聊天消息与知识库的关联，避免外键限制阻止删除
        
        Args:
            db: 异步数据库会话
            kb_id: 知识库ID
            
        Returns:
            bool: 删除成功返回True，否则返回False
        """
        kb = await self.get_kb(db, kb_id)
        if not kb:
            return False
        # 先解除聊天消息与知识库的关联，避免外键限制阻止删除
        await db.execute(
            update(ChatMessage)
            .where(ChatMessage.kb_id == kb_id)
            .values(kb_id=None)
        )
        await db.flush()
        await db.delete(kb)
        await db.commit()
        return True

    # ========== 文档 (Document) 操作 ==========

    async def create_document(
        self,
        db: AsyncSession,
        kb_id: int,
        file_name: str,
        file_path: str,
        file_type: str,
        file_size: int
    ) -> Document:
        """创建新的文档
        
        Args:
            db: 异步数据库会话
            kb_id: 知识库ID
            file_name: 文件名
            file_path: 文件路径
            file_type: 文件类型
            file_size: 文件大小（字节）
            
        Returns:
            Document: 创建的文档对象
        """
        doc = Document(
            kb_id=kb_id,
            file_name=file_name,
            file_path=file_path,
            file_type=file_type,
            file_size=file_size,
            status=DocStatus.PROCESSING # 初始状态为处理中
        )
        db.add(doc)
        await db.commit()
        await db.refresh(doc)
        return doc

    async def get_kb_documents(self, db: AsyncSession, kb_id: int) -> List[Document]:
        """获取知识库的所有文档
        
        Args:
            db: 异步数据库会话
            kb_id: 知识库ID
            
        Returns:
            List[Document]: 文档列表，按创建时间倒序排列
        """
        statement = select(Document).where(Document.kb_id == kb_id).order_by(desc(Document.created_at))
        result = await db.execute(statement)
        return list(result.scalars().all())

    async def get_document(self, db: AsyncSession, doc_id: int) -> Optional[Document]:
        """根据ID获取文档
        
        Args:
            db: 异步数据库会话
            doc_id: 文档ID
            
        Returns:
            Optional[Document]: 文档对象，如果不存在则返回None
        """
        return await db.get(Document, doc_id)

    async def update_document_status(
        self,
        db: AsyncSession,
        doc_id: int,
        status: DocStatus,
        chunk_count: Optional[int] = None,
        error_msg: Optional[str] = None
    ):
        """更新文档状态
        
        Args:
            db: 异步数据库会话
            doc_id: 文档ID
            status: 新的文档状态
            chunk_count: 分块数量
            error_msg: 错误信息
        """
        doc = await self.get_document(db, doc_id)
        if doc:
            doc.status = status
            if chunk_count is not None:
                doc.chunk_count = chunk_count
            if error_msg is not None:
                doc.error_msg = error_msg
            db.add(doc)
            await db.commit()

    # ========== 分块 (Chunk) 操作 ==========

    async def create_chunk(
        self,
        db: AsyncSession,
        doc_id: int,
        parent_id: str,
        content: str,
        vector_id: str,
        chunk_index: int,
        token_count: int = 0,
        structured_meta: Optional[dict] = None
    ) -> DocumentChunk:
        """创建新的文档分块
        
        Args:
            db: 异步数据库会话
            doc_id: 文档ID
            parent_id: 父分块ID
            content: 分块内容
            vector_id: 向量数据库中的ID
            chunk_index: 分块索引
            token_count: Token数量
            structured_meta: 结构化元数据
            
        Returns:
            DocumentChunk: 创建的分块对象
        """
        chunk = DocumentChunk(
            doc_id=doc_id,
            parent_id=parent_id,
            content=content,
            vector_id=vector_id,
            chunk_index=chunk_index,
            token_count=token_count,
            structured_meta=structured_meta
        )
        db.add(chunk)
        await db.commit()
        return chunk

    async def get_document_chunks(self, db: AsyncSession, doc_id: int) -> List[DocumentChunk]:
        """获取文档的所有分块
        
        Args:
            db: 异步数据库会话
            doc_id: 文档ID
            
        Returns:
            List[DocumentChunk]: 分块列表，按分块索引排序
        """
        statement = select(DocumentChunk).where(DocumentChunk.doc_id == doc_id).order_by(DocumentChunk.chunk_index.asc())
        result = await db.execute(statement)
        return list(result.scalars().all())

    async def get_document_chunk_by_id(
        self,
        db: AsyncSession,
        doc_id: int,
        chunk_id: int,
    ) -> Optional[DocumentChunk]:
        """按文档ID和分块ID获取单条分片
        
        Args:
            db: 异步数据库会话
            doc_id: 文档ID
            chunk_id: 分块ID
            
        Returns:
            Optional[DocumentChunk]: 分块对象，如果不存在则返回None
        """
        statement = select(DocumentChunk).where(
            DocumentChunk.doc_id == doc_id,
            DocumentChunk.id == chunk_id,
        )
        result = await db.execute(statement)
        return result.scalar_one_or_none()

    async def get_document_chunk_by_index(
        self,
        db: AsyncSession,
        doc_id: int,
        chunk_index: int,
    ) -> Optional[DocumentChunk]:
        """按文档ID和分块序号获取单条分片
        
        Args:
            db: 异步数据库会话
            doc_id: 文档ID
            chunk_index: 分块索引
            
        Returns:
            Optional[DocumentChunk]: 分块对象，如果不存在则返回None
        """
        statement = select(DocumentChunk).where(
            DocumentChunk.doc_id == doc_id,
            DocumentChunk.chunk_index == chunk_index,
        )
        result = await db.execute(statement)
        return result.scalar_one_or_none()

    async def delete_document_chunks(self, db: AsyncSession, doc_id: int) -> int:
        """删除文档的所有分块
        
        Args:
            db: 异步数据库会话
            doc_id: 文档ID
            
        Returns:
            int: 被删除的分块数量
        """
        statement = select(DocumentChunk).where(DocumentChunk.doc_id == doc_id)
        result = await db.execute(statement)
        chunks = list(result.scalars().all())
        deleted = 0
        for chunk in chunks:
            await db.delete(chunk)
            deleted += 1
        await db.commit()
        return deleted

    async def delete_document(self, db: AsyncSession, doc_id: int) -> bool:
        """删除文档
        
        Args:
            db: 异步数据库会话
            doc_id: 文档ID
            
        Returns:
            bool: 删除成功返回True，否则返回False
        """
        doc = await self.get_document(db, doc_id)
        if not doc:
            return False
        await db.delete(doc)
        await db.commit()
        return True

    async def get_kb_chunks(self, db: AsyncSession, kb_id: int) -> List[DocumentChunk]:
        """获取知识库的所有已完成文档的分块
        
        Args:
            db: 异步数据库会话
            kb_id: 知识库ID
            
        Returns:
            List[DocumentChunk]: 分块列表
        """
        statement = (
            select(DocumentChunk)
            .join(Document, Document.id == DocumentChunk.doc_id)
            .where(Document.kb_id == kb_id, Document.status == DocStatus.COMPLETED)
            .order_by(DocumentChunk.id.asc())
        )
        result = await db.execute(statement)
        return list(result.scalars().all())

    async def get_completed_documents(self, db: AsyncSession, kb_id: int) -> List[Document]:
        """获取知识库的所有已完成文档
        
        Args:
            db: 异步数据库会话
            kb_id: 知识库ID
            
        Returns:
            List[Document]: 已完成的文档列表
        """
        statement = (
            select(Document)
            .where(Document.kb_id == kb_id, Document.status == DocStatus.COMPLETED)
            .order_by(desc(Document.created_at))
        )
        result = await db.execute(statement)
        return list(result.scalars().all())


# 实例化
kb_crud = KnowledgeCRUD()
