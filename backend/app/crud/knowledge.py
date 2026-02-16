"""crud/knowledge.py."""
from typing import List, Optional
from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select, desc, update
from app.models.knowledge import KnowledgeBase, Document, DocumentChunk, DocStatus
from app.models.chat import ChatMessage

class KnowledgeCRUD:

    # ========== 知识库 (KnowledgeBase) 操作 ==========

    """KnowledgeCRUD ??"""
    async def create_kb(self, db: AsyncSession, user_id: int, name: str, description: Optional[str] = None) -> KnowledgeBase:
        """create_kb ?????"""
        kb = KnowledgeBase(user_id=user_id, name=name, description=description)
        db.add(kb)
        await db.commit()
        await db.refresh(kb)
        return kb

    async def get_user_kbs(self, db: AsyncSession, user_id: int) -> List[KnowledgeBase]:
        """get_user_kbs ?????"""
        statement = select(KnowledgeBase).where(KnowledgeBase.user_id == user_id).order_by(desc(KnowledgeBase.created_at))
        result = await db.execute(statement)
        return list(result.scalars().all())

    async def get_kb(self, db: AsyncSession, kb_id: int) -> Optional[KnowledgeBase]:
        """get_kb ?????"""
        return await db.get(KnowledgeBase, kb_id)

    async def delete_kb(self, db: AsyncSession, kb_id: int) -> bool:
        """delete_kb ?????"""
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
        """create_document ?????"""
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
        """get_kb_documents ?????"""
        statement = select(Document).where(Document.kb_id == kb_id).order_by(desc(Document.created_at))
        result = await db.execute(statement)
        return list(result.scalars().all())

    async def get_document(self, db: AsyncSession, doc_id: int) -> Optional[Document]:
        """get_document ?????"""
        return await db.get(Document, doc_id)

    async def update_document_status(
        self,
        db: AsyncSession,
        doc_id: int,
        status: DocStatus,
        chunk_count: Optional[int] = None,
        error_msg: Optional[str] = None
    ):
        """update_document_status ?????"""
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
        """create_chunk ?????"""
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
        """get_document_chunks ?????"""
        statement = select(DocumentChunk).where(DocumentChunk.doc_id == doc_id).order_by(DocumentChunk.chunk_index.asc())
        result = await db.execute(statement)
        return list(result.scalars().all())

    async def get_document_chunk_by_id(
        self,
        db: AsyncSession,
        doc_id: int,
        chunk_id: int,
    ) -> Optional[DocumentChunk]:
        """按文档 + chunk 主键获取单条分片。"""
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
        """按文档 + chunk 序号获取单条分片。"""
        statement = select(DocumentChunk).where(
            DocumentChunk.doc_id == doc_id,
            DocumentChunk.chunk_index == chunk_index,
        )
        result = await db.execute(statement)
        return result.scalar_one_or_none()

    async def delete_document_chunks(self, db: AsyncSession, doc_id: int) -> int:
        """delete_document_chunks ?????"""
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
        """delete_document ?????"""
        doc = await self.get_document(db, doc_id)
        if not doc:
            return False
        await db.delete(doc)
        await db.commit()
        return True

    async def get_kb_chunks(self, db: AsyncSession, kb_id: int) -> List[DocumentChunk]:
        """get_kb_chunks ?????"""
        statement = (
            select(DocumentChunk)
            .join(Document, Document.id == DocumentChunk.doc_id)
            .where(Document.kb_id == kb_id, Document.status == DocStatus.COMPLETED)
            .order_by(DocumentChunk.id.asc())
        )
        result = await db.execute(statement)
        return list(result.scalars().all())

    async def get_completed_documents(self, db: AsyncSession, kb_id: int) -> List[Document]:
        """get_completed_documents ?????"""
        statement = (
            select(Document)
            .where(Document.kb_id == kb_id, Document.status == DocStatus.COMPLETED)
            .order_by(desc(Document.created_at))
        )
        result = await db.execute(statement)
        return list(result.scalars().all())

# 实例化
kb_crud = KnowledgeCRUD()
