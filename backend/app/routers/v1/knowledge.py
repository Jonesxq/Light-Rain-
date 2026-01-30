import os
import uuid
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import get_db
from app.core.deps import get_current_user
from app.models.user import User
from app.crud.knowledge import kb_crud
from app.services.knowledge import kb_service
from app.services.rag_evaluation import rag_evaluation_service
from app.schemas.knowledge import (
    DocumentResponse,
    KnowledgeBaseResponse,
    KnowledgeBaseCreate,
    KnowledgeEvalRequest,
    KnowledgeEvalResponse,
)

router = APIRouter(prefix="/knowledge", tags=["Knowledge Base"])

# 允许上传的文件格式
ALLOWED_EXTENSIONS = {".pdf", ".docx", ".txt", ".md"}
# 文件保存路径
UPLOAD_DIR = "static/uploads/kb"
# 单个文件最大大小（字节），避免一次性占用过多内存
MAX_UPLOAD_SIZE = 50 * 1024 * 1024  # 50MB


# --- 1. 知识库管理 ---
@router.post("/create", response_model=KnowledgeBaseResponse)
async def create_knowledge_base(
    kb_in: KnowledgeBaseCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """创建知识库并返回 kb_id"""
    # 适配你现有的 CRUD 方法签名: (db, user_id, name, description)
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
    """获取当前用户的知识库列表"""
    return await kb_crud.get_user_kbs(db, user_id=current_user.id)


@router.delete("/{kb_id}")
async def delete_kb(
        kb_id: int,
        current_user: User = Depends(get_current_user),
        db: AsyncSession = Depends(get_db)
):
    """删除知识库（会级联删除文档与切片记录）"""
    kb = await kb_crud.get_kb(db, kb_id)
    if not kb or kb.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Knowledge base not found")

    success = await kb_crud.delete_kb(db, kb_id)
    return {"success": success}

@router.get("/{kb_id}/documents", response_model=list[DocumentResponse])
async def list_kb_documents(
        kb_id: int,
        current_user: User = Depends(get_current_user),
        db: AsyncSession = Depends(get_db)
):
    """获取指定知识库下的所有文档"""
    kb = await kb_crud.get_kb(db, kb_id)
    if not kb or kb.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Knowledge base not found")

    return await kb_crud.get_kb_documents(db, kb_id)


@router.delete("/{kb_id}/documents/{doc_id}")
async def delete_kb_document(
        kb_id: int,
        doc_id: int,
        current_user: User = Depends(get_current_user),
        db: AsyncSession = Depends(get_db)
):
    """删除指定知识库下的文档（含向量与本地文件）"""
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
    """对知识库进行自动评估（生成样本 -> 检索 -> 回答 -> 评分）"""
    kb = await kb_crud.get_kb(db, kb_id)
    if not kb or kb.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Knowledge base not found")

    result = await rag_evaluation_service.evaluate_kb(
        kb_id=kb_id,
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
    # 1) 校验知识库权限
    kb = await kb_crud.get_kb(db, kb_id)
    if not kb or kb.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Knowledge base not found")

    # 2) 校验文件后缀
    file_ext = os.path.splitext(file.filename)[1].lower()
    if file_ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=400, detail=f"Unsupported file type: {file_ext}")

    # 3) 保存原始文件到本地路径
    if not os.path.exists(UPLOAD_DIR):
        os.makedirs(UPLOAD_DIR)

    unique_filename = f"{uuid.uuid4()}{file_ext}"
    file_path = os.path.join(UPLOAD_DIR, unique_filename)
    file_size = 0
    # 采用分块写入，降低内存占用并支持大文件
    with open(file_path, "wb") as f:
        while True:
            chunk = await file.read(1024 * 1024)  # 每次 1MB
            if not chunk:
                break
            file_size += len(chunk)
            if file_size > MAX_UPLOAD_SIZE:
                # 超过限制立即终止并删除文件
                f.close()
                if os.path.exists(file_path):
                    os.remove(file_path)
                raise HTTPException(status_code=413, detail="File too large")
            f.write(chunk)

    # 4) 数据库创建文档记录（状态: PROCESSING）
    doc = await kb_crud.create_document(
        db,
        kb_id=kb_id,
        file_name=file.filename,
        file_path=file_path,
        file_type=file_ext,
        file_size=file_size
    )

    # 5) 提交后台任务：解析 -> 切片 -> 向量化 -> 存入 Milvus
    background_tasks.add_task(kb_service.ingest_document, doc.id)

    return doc
