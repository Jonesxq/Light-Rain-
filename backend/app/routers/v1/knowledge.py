"""知识库API路由模块 - 提供知识库管理、文档上传、分块预览等功能"""
import os
import uuid
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, BackgroundTasks
from sqlalchemy import func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select, desc
from app.core.database import get_db
from app.core.deps import get_current_user
from app.models.user import User
from app.models.knowledge import DocStatus, Document, DocumentChunk
from app.crud.knowledge import kb_crud
from app.services.knowledge import kb_service
from app.services.rag_evaluation import rag_evaluation_service
from app.schemas.knowledge import (
    DocumentResponse,
    KnowledgeBaseResponse,
    KnowledgeBaseCreate,
    KnowledgeEvalRequest,
    KnowledgeEvalResponse,
    KnowledgeChunkPreviewResponse,
)

router = APIRouter(prefix="/knowledge", tags=["Knowledge Base"])

# 允许上传的文件格式
ALLOWED_EXTENSIONS = {".pdf", ".docx", ".txt", ".md"}
# 文件保存路径
UPLOAD_DIR = "static/uploads/kb"
# 单个文件最大大小（字节），避免一次性占用过多内存
MAX_UPLOAD_SIZE = 50 * 1024 * 1024  # 50MB 上限


async def _get_owned_completed_doc_or_404(
    db: AsyncSession,
    current_user: User,
    doc_id: int,
) -> Document:
    """校验文档存在、归属与处理状态
    
    确保文档存在、属于当前用户且处理完成
    
    Args:
        db: 数据库会话
        current_user: 当前登录用户
        doc_id: 文档ID
        
    Returns:
        Document: 验证通过的文档对象
        
    Raises:
        HTTPException: 文档不存在返回404，未处理完成返回409
    """
    doc = await kb_crud.get_document(db, doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    kb = await kb_crud.get_kb(db, doc.kb_id)
    if not kb or kb.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Document not found")

    if doc.status != DocStatus.COMPLETED:
        raise HTTPException(status_code=409, detail="Document is still processing")
    return doc


def _build_chunk_preview_payload(
    doc: Document,
    preview: dict,
    chunk_index: int,
    chunk_id: int | None = None,
) -> dict:
    """统一构建分块预览响应
    
    Args:
        doc: 文档对象
        preview: 分块预览数据
        chunk_index: 分块索引
        chunk_id: 分块ID（可选）
        
    Returns:
        dict: 格式化的分块预览响应
    """
    structured_meta = preview.get("structured_meta") or {}
    loc_meta = structured_meta.get("loc", {}) if isinstance(structured_meta.get("loc"), dict) else {}
    return {
        "doc_id": doc.id,
        "chunk_id": chunk_id,
        "chunk_index": chunk_index,
        "file_name": doc.file_name,
        "file_type": doc.file_type,
        "content": preview.get("content") or "",
        "pages": loc_meta.get("pages"),
        "slides": loc_meta.get("slides"),
        "paragraphs": loc_meta.get("paragraphs"),
        "tables": loc_meta.get("tables"),
        "md_headings": loc_meta.get("md_headings"),
    }


# --- 1. 知识库管理 ---
@router.post("/create", response_model=KnowledgeBaseResponse)
async def create_knowledge_base(
    kb_in: KnowledgeBaseCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """创建知识库
    
    Args:
        kb_in: 知识库创建数据（包含名称和描述）
        current_user: 当前登录用户
        db: 数据库会话
        
    Returns:
        KnowledgeBaseResponse: 创建的知识库信息
    """
    return await kb_crud.create_kb(
        db,
        user_id=current_user.id,
        name=kb_in.name,
        description=kb_in.description
    )


@router.get("/list", response_model=list[KnowledgeBaseResponse])
async def list_kbs(
        current_user: User = Depends(get_current_user),
        db: AsyncSession = Depends(get_db)
):
    """获取当前用户的知识库列表
    
    Args:
        current_user: 当前登录用户
        db: 数据库会话
        
    Returns:
        list[KnowledgeBaseResponse]: 知识库列表
    """
    return await kb_crud.get_user_kbs(db, user_id=current_user.id)


@router.delete("/{kb_id}")
async def delete_kb(
        kb_id: int,
        current_user: User = Depends(get_current_user),
        db: AsyncSession = Depends(get_db)
):
    """删除知识库
    
    同时删除知识库中的所有文档和向量数据
    
    Args:
        kb_id: 知识库ID
        current_user: 当前登录用户
        db: 数据库会话
        
    Returns:
        dict: 操作成功标识
        
    Raises:
        HTTPException: 知识库不存在或无权限时返回404错误
    """
    kb = await kb_crud.get_kb(db, kb_id)
    if not kb or kb.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Knowledge base not found")

    success = await kb_service.delete_kb(kb_id)
    return {"success": success}

@router.get("/{kb_id}/documents", response_model=list[DocumentResponse])
async def list_kb_documents(
        kb_id: int,
        current_user: User = Depends(get_current_user),
        db: AsyncSession = Depends(get_db)
):
    """获取知识库中的文档列表
    
    包括每个文档的处理状态、分块数量等信息
    
    Args:
        kb_id: 知识库ID
        current_user: 当前登录用户
        db: 数据库会话
        
    Returns:
        list[DocumentResponse]: 文档列表
        
    Raises:
        HTTPException: 知识库不存在或无权限时返回404错误
    """
    kb = await kb_crud.get_kb(db, kb_id)
    if not kb or kb.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Knowledge base not found")

    statement = (
        select(Document, func.count(DocumentChunk.id).label("processed_chunks"))
        .outerjoin(DocumentChunk, DocumentChunk.doc_id == Document.id)
        .where(Document.kb_id == kb_id)
        .group_by(Document.id)
        .order_by(desc(Document.created_at))
    )
    result = await db.execute(statement)
    rows = result.all()

    payload = []
    for doc, processed_chunks in rows:
        payload.append(
            {
                "id": doc.id,
                "file_name": doc.file_name,
                "status": doc.status,
                "chunk_count": doc.chunk_count,
                "processed_chunks": processed_chunks or 0,
                "error_msg": doc.error_msg,
                "created_at": doc.created_at,
            }
        )

    return payload


@router.get("/documents/{doc_id}/chunks/{chunk_index}", response_model=KnowledgeChunkPreviewResponse)
async def get_chunk_preview(
        doc_id: int,
        chunk_index: int,
        current_user: User = Depends(get_current_user),
        db: AsyncSession = Depends(get_db)
):
    """根据索引获取文档分块预览
    
    Args:
        doc_id: 文档ID
        chunk_index: 分块索引
        current_user: 当前登录用户
        db: 数据库会话
        
    Returns:
        KnowledgeChunkPreviewResponse: 分块预览内容
        
    Raises:
        HTTPException: 文档或分块不存在时返回404
    """
    doc = await _get_owned_completed_doc_or_404(db, current_user, doc_id)
    chunk = await kb_crud.get_document_chunk_by_index(db, doc_id=doc_id, chunk_index=chunk_index)

    preview = None
    if chunk:
        preview = kb_service.get_raw_chunk_preview_by_parent_id(doc, chunk.parent_id)
        if not preview and chunk.content:
            preview = {
                "content": chunk.content,
                "structured_meta": chunk.structured_meta or {},
            }
    if not preview:
        preview = kb_service.get_raw_chunk_preview(doc, chunk_index)
    if not preview:
        raise HTTPException(status_code=404, detail="Chunk not found")

    resolved_chunk_index = chunk.chunk_index if chunk else chunk_index
    resolved_chunk_id = chunk.id if chunk else None
    return _build_chunk_preview_payload(
        doc=doc,
        preview=preview,
        chunk_index=resolved_chunk_index,
        chunk_id=resolved_chunk_id,
    )


@router.get("/documents/{doc_id}/chunks/by-id/{chunk_id}", response_model=KnowledgeChunkPreviewResponse)
async def get_chunk_preview_by_id(
        doc_id: int,
        chunk_id: int,
        current_user: User = Depends(get_current_user),
        db: AsyncSession = Depends(get_db)
):
    """根据分块ID获取文档分块预览
    
    Args:
        doc_id: 文档ID
        chunk_id: 分块ID
        current_user: 当前登录用户
        db: 数据库会话
        
    Returns:
        KnowledgeChunkPreviewResponse: 分块预览内容
        
    Raises:
        HTTPException: 文档或分块不存在时返回404
    """
    doc = await _get_owned_completed_doc_or_404(db, current_user, doc_id)
    chunk = await kb_crud.get_document_chunk_by_id(db, doc_id=doc_id, chunk_id=chunk_id)
    if not chunk:
        raise HTTPException(status_code=404, detail="Chunk not found")

    preview = kb_service.get_raw_chunk_preview_by_parent_id(doc, chunk.parent_id)
    if not preview and chunk.content:
        preview = {
            "content": chunk.content,
            "structured_meta": chunk.structured_meta or {},
        }
    if not preview:
        raise HTTPException(status_code=404, detail="Chunk not found")

    return _build_chunk_preview_payload(
        doc=doc,
        preview=preview,
        chunk_index=chunk.chunk_index,
        chunk_id=chunk.id,
    )


@router.post("/documents/{doc_id}/reindex")
async def reindex_document(
        doc_id: int,
        background_tasks: BackgroundTasks,
        current_user: User = Depends(get_current_user),
        db: AsyncSession = Depends(get_db)
):
    """重新索引文档
    
    重新解析文档、分块并向量化，异步执行
    
    Args:
        doc_id: 文档ID
        background_tasks: 后台任务管理器
        current_user: 当前登录用户
        db: 数据库会话
        
    Returns:
        dict: 操作成功标识
        
    Raises:
        HTTPException: 文档不存在返回404，正在处理返回409
    """
    doc = await kb_crud.get_document(db, doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    kb = await kb_crud.get_kb(db, doc.kb_id)
    if not kb or kb.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Document not found")

    if doc.status in (DocStatus.PROCESSING, DocStatus.UPLOADING):
        raise HTTPException(status_code=409, detail="Document is still processing")

    background_tasks.add_task(kb_service.reindex_document, doc_id)
    return {"success": True}


@router.delete("/{kb_id}/documents/{doc_id}")
async def delete_kb_document(
        kb_id: int,
        doc_id: int,
        current_user: User = Depends(get_current_user),
        db: AsyncSession = Depends(get_db)
):
    """删除知识库中的文档
    
    同时删除文档的所有分块和向量数据
    
    Args:
        kb_id: 知识库ID
        doc_id: 文档ID
        current_user: 当前登录用户
        db: 数据库会话
        
    Returns:
        dict: 操作成功标识
        
    Raises:
        HTTPException: 知识库或文档不存在时返回404
    """
    kb = await kb_crud.get_kb(db, kb_id)
    if not kb or kb.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Knowledge base not found")

    success = await kb_service.delete_document(kb_id, doc_id)
    if not success:
        raise HTTPException(status_code=404, detail="Document not found")
    return {"success": True}


# --- 评估：无评测集自动生成 ---
@router.post("/{kb_id}/evaluate", response_model=KnowledgeEvalResponse)
async def evaluate_kb(
        kb_id: int,
        payload: KnowledgeEvalRequest,
        current_user: User = Depends(get_current_user),
        db: AsyncSession = Depends(get_db)
):
    """评估知识库的RAG效果
    
    自动生成测试问题并评估检索和回答质量
    
    Args:
        kb_id: 知识库ID
        payload: 评估配置参数
        current_user: 当前登录用户
        db: 数据库会话
        
    Returns:
        KnowledgeEvalResponse: 评估结果
        
    Raises:
        HTTPException: 知识库不存在或无权限时返回404
    """
    kb = await kb_crud.get_kb(db, kb_id)
    if not kb or kb.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Knowledge base not found")

    result = await rag_evaluation_service.evaluate_kb(
        kb_id=kb_id,
        user_id=current_user.id,
        sample_size=payload.sample_size,
        top_k=payload.top_k,
        generate_model=payload.generate_model,
        answer_model=payload.answer_model,
        judge_model=payload.judge_model,
        max_chunk_chars=payload.max_chunk_chars
    )
    return result


# --- 2. 文档上传 ---
@router.post("/{kb_id}/upload", response_model=DocumentResponse)
async def upload_document(
        kb_id: int,
        background_tasks: BackgroundTasks,
        file: UploadFile = File(...),
        current_user: User = Depends(get_current_user),
        db: AsyncSession = Depends(get_db)
):
    """上传文档到知识库
    
    支持PDF、DOCX、TXT、MD格式，最大50MB，上传后异步处理
    
    Args:
        kb_id: 知识库ID
        background_tasks: 后台任务管理器
        file: 上传的文件
        current_user: 当前登录用户
        db: 数据库会话
        
    Returns:
        DocumentResponse: 上传的文档信息
        
    Raises:
        HTTPException: 知识库无权限返回404，文件格式不支持返回400，文件过大返回413
    """
    kb = await kb_crud.get_kb(db, kb_id)
    if not kb or kb.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Knowledge base not found")

    file_ext = os.path.splitext(file.filename)[1].lower()
    if file_ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=400, detail=f"Unsupported file type: {file_ext}")

    if not os.path.exists(UPLOAD_DIR):
        os.makedirs(UPLOAD_DIR)

    unique_filename = f"{uuid.uuid4()}{file_ext}"
    file_path = os.path.join(UPLOAD_DIR, unique_filename)
    file_size = 0
    with open(file_path, "wb") as f:
        while True:
            chunk = await file.read(1024 * 1024)
            if not chunk:
                break
            file_size += len(chunk)
            if file_size > MAX_UPLOAD_SIZE:
                f.close()
                if os.path.exists(file_path):
                    os.remove(file_path)
                raise HTTPException(status_code=413, detail="File too large")
            f.write(chunk)

    doc = await kb_crud.create_document(
        db,
        kb_id=kb_id,
        file_name=file.filename,
        file_path=file_path,
        file_type=file_ext,
        file_size=file_size
    )

    background_tasks.add_task(kb_service.ingest_document, doc.id)

    return doc



