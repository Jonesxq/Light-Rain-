"""routers/v1/chat.py."""
import json
import os
import uuid
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import get_current_user, get_current_superuser
from app.crud.chat_attachment import chat_attachment_crud
from app.crud.knowledge import kb_crud
from app.models.user import User
from app.models.chat import ChatRole
from app.schemas.chat import (
    ChatSessionResponse,
    ChatSessionCreate,
    ChatSessionUpdate,
    ChatMessageResponse,
    ChatRequest, KnowledgeChatRequest, KnowledgeChatResponse,
    ChatRegenerateRequest, FavoriteUpdateRequest, ChatAttachmentResponse,
    ChatSuggestionRequest, ChatSuggestionResponse,
    ChatPromptSnapshotResponse,
)
from app.core.logger import logger_manager
from app.crud.chat import chat_crud
from app.crud.chat_prompt_snapshot import chat_prompt_snapshot_crud
from app.services.chat import chat_service
from app.services.knowledge import kb_service
from app.services.temp_context import temp_context_service



logger = logger_manager.get_logger(__name__)
router = APIRouter(prefix="/chat", tags=["Chat"])

ATTACHMENT_ALLOWED_EXTENSIONS = {".pdf", ".docx", ".txt", ".md", ".png", ".jpg", ".jpeg"}
ATTACHMENT_UPLOAD_DIR = "static/uploads/temp_context"
ATTACHMENT_MAX_SIZE = 10 * 1024 * 1024  # 10MB

def _build_attachment_preview(text: Optional[str], max_len: int = 200) -> str:
    """build preview text for attachment."""
    if not text:
        return ""
    clean = text.replace("\r", " ").replace("\n", " ").strip()
    if len(clean) <= max_len:
        return clean
    return clean[:max_len] + "…"

@router.post("/sessions", response_model=ChatSessionResponse)
async def create_session(
    session_data: ChatSessionCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """create_session ?????"""
    return await chat_crud.create_session(db, current_user.id, session_data.title)

@router.get("/sessions", response_model=List[ChatSessionResponse])
async def get_my_sessions(
    skip: int = 0,
    limit: int = 20,
    q: Optional[str] = None,
    include_archived: bool = False,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """get_my_sessions ?????"""
    return await chat_crud.get_user_sessions(
        db,
        current_user.id,
        skip,
        limit,
        q=q,
        include_archived=include_archived,
    )

@router.patch("/sessions/{session_id}", response_model=ChatSessionResponse)
async def update_session(
    session_id: int,
    payload: ChatSessionUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """update_session ?????"""
    session = await chat_crud.get_session(db, session_id)
    if not session or session.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Session not found")
    updated = await chat_crud.update_session(
        db,
        session_id=session_id,
        title=payload.title,
        is_pinned=payload.is_pinned,
        is_archived=payload.is_archived,
        tags=payload.tags,
    )
    if not updated:
        raise HTTPException(status_code=404, detail="Session not found")
    return updated


@router.delete("/sessions/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_session(
    session_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """delete_session ?????"""
    success = await chat_crud.delete_session(db, session_id, current_user.id)
    if not success:
        raise HTTPException(status_code=404, detail="Session not found")


@router.post("/sessions/{session_id}/suggestions", response_model=ChatSuggestionResponse)
async def get_chat_suggestions(
    session_id: int,
    payload: ChatSuggestionRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """get_chat_suggestions ?????"""
    session = await chat_crud.get_session(db, session_id)
    if not session or session.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Session not found")
    suggestions = await chat_service.suggest_followups(
        db=db,
        user_id=current_user.id,
        session_id=session_id,
        limit=payload.limit,
        model=payload.model,
    )
    return {"session_id": session_id, "suggestions": suggestions}


@router.post("/messages/{message_id}/meme", response_model=ChatMessageResponse)
async def generate_meme(
    message_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """generate_meme ?????"""
    try:
        return await chat_service.generate_meme(db, current_user.id, message_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc))
    except Exception:
        raise HTTPException(status_code=500, detail="Meme generation failed")

@router.get("/attachments", response_model=List[ChatAttachmentResponse])
async def list_attachments(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """list_attachments ?????"""
    attachments = await chat_attachment_crud.list_attachments(db, current_user.id)
    payload = []
    for att in attachments:
        preview_source = att.extracted_text
        if not preview_source and att.chunks:
            preview_source = str(att.chunks[0])
        payload.append(
            {
                "id": att.id,
                "file_name": att.file_name,
                "file_type": att.file_type,
                "file_size": att.file_size,
                "preview": _build_attachment_preview(preview_source),
                "created_at": att.created_at,
            }
        )
    return payload


@router.post("/attachments/upload", response_model=ChatAttachmentResponse)
async def upload_attachment(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """upload_attachment ?????"""
    if not file.filename:
        raise HTTPException(status_code=400, detail="File name missing")
    file_ext = os.path.splitext(file.filename)[1].lower()
    if file_ext not in ATTACHMENT_ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=400, detail=f"Unsupported file type: {file_ext}")

    if not os.path.exists(ATTACHMENT_UPLOAD_DIR):
        os.makedirs(ATTACHMENT_UPLOAD_DIR)

    unique_filename = f"{uuid.uuid4()}{file_ext}"
    file_path = os.path.join(ATTACHMENT_UPLOAD_DIR, unique_filename)
    file_size = 0
    try:
        with open(file_path, "wb") as f:
            while True:
                chunk = await file.read(1024 * 1024)
                if not chunk:
                    break
                file_size += len(chunk)
                if file_size > ATTACHMENT_MAX_SIZE:
                    f.close()
                    if os.path.exists(file_path):
                        os.remove(file_path)
                    raise HTTPException(status_code=413, detail="File too large")
                f.write(chunk)
    finally:
        await file.close()

    try:
        attachment = await temp_context_service.create_attachment(
            db=db,
            user_id=current_user.id,
            file_name=file.filename,
            file_type=file_ext,
            file_size=file_size,
            file_path=file_path,
        )
    except ValueError as exc:
        if os.path.exists(file_path):
            os.remove(file_path)
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception:
        if os.path.exists(file_path):
            os.remove(file_path)
        raise HTTPException(status_code=500, detail="Attachment processing failed")

    preview_source = attachment.extracted_text
    if not preview_source and attachment.chunks:
        preview_source = str(attachment.chunks[0])

    return {
        "id": attachment.id,
        "file_name": attachment.file_name,
        "file_type": attachment.file_type,
        "file_size": attachment.file_size,
        "preview": _build_attachment_preview(preview_source),
        "created_at": attachment.created_at,
    }


@router.delete("/attachments/{attachment_id}")
async def delete_attachment(
    attachment_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """delete_attachment ?????"""
    attachment = await chat_attachment_crud.get_attachment(db, attachment_id)
    if not attachment or attachment.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Attachment not found")
    success = await chat_attachment_crud.delete_attachment(db, attachment_id)
    if not success:
        raise HTTPException(status_code=404, detail="Attachment not found")
    try:
        if attachment.file_path and os.path.exists(attachment.file_path):
            os.remove(attachment.file_path)
    except Exception:
        pass
    return {"success": True}

# ========== 聊天交互 ==========

@router.get("/sessions/{session_id}/messages", response_model=List[ChatMessageResponse])
async def get_history(
        session_id: int,
        current_user: User = Depends(get_current_user),
        db: AsyncSession = Depends(get_db)
):
    """get_history ?????"""
    session = await chat_crud.get_session(db, session_id)
    if not session or session.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Session not found")

    return await chat_crud.get_session_messages(db, session_id)


@router.post("/sessions/{session_id}/send", response_model=ChatMessageResponse)
async def send_message(
        session_id: int,
        chat_req: ChatRequest,
        current_user: User = Depends(get_current_user),
        db: AsyncSession = Depends(get_db)
):
    """send_message ?????"""
    try:
        # LangChain 会在内部处理 API 调用
        ai_message = await chat_service.process_chat(
            db,
            current_user.id,
            session_id,
            chat_req
        )
        return ai_message
    except ValueError as e:
        # 捕获 Service 层抛出的错误
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(e))
    except Exception as e:
        # 捕获其他未知错误
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Internal Chat Error")

@router.post("/sessions/{session_id}/stream")
async def stream_message(
        session_id: int,
        chat_req: ChatRequest,
        current_user: User = Depends(get_current_user),
        db: AsyncSession = Depends(get_db)
):
    """stream_message ?????"""
    session = await chat_crud.get_session(db, session_id)
    if not session or session.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Session not found")

    async def event_generator():
        """event_generator ?????"""
        try:
            async for payload in chat_service.stream_chat(
                db,
                current_user.id,
                session_id,
                chat_req
            ):
                yield payload
        except Exception as e:
            error_payload = json.dumps({"event": "error", "message": str(e)})
            yield f"data: {error_payload}\n\n"

    headers = {"Cache-Control": "no-cache", "Connection": "keep-alive"}
    return StreamingResponse(event_generator(), media_type="text/event-stream", headers=headers)


@router.patch("/messages/{message_id}/favorite", response_model=ChatMessageResponse)
async def update_favorite(
    message_id: int,
    payload: FavoriteUpdateRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """update_favorite ?????"""
    message = await chat_crud.get_message(db, message_id)
    if not message:
        raise HTTPException(status_code=404, detail="Message not found")
    session = await chat_crud.get_session(db, message.session_id)
    if not session or session.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Message not found")
    if message.role != ChatRole.ASSISTANT:
        raise HTTPException(status_code=400, detail="只能收藏助手消息")
    updated = await chat_crud.set_message_favorite(db, message_id, payload.is_favorite)
    if not updated:
        raise HTTPException(status_code=404, detail="Message not found")
    return updated


@router.post("/messages/{message_id}/resend/stream")
async def resend_message_stream(
    message_id: int,
    chat_req: ChatRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """resend_message_stream ?????"""
    message = await chat_crud.get_message(db, message_id)
    if not message:
        raise HTTPException(status_code=404, detail="Message not found")
    session = await chat_crud.get_session(db, message.session_id)
    if not session or session.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Message not found")
    if message.kb_id is not None:
        kb = await kb_crud.get_kb(db, message.kb_id)
        if not kb or kb.user_id != current_user.id:
            raise HTTPException(status_code=403, detail="无权访问该知识库")

    async def event_generator():
        """event_generator ?????"""
        try:
            async for payload in chat_service.stream_resend(
                db=db,
                user_id=current_user.id,
                message_id=message_id,
                new_message=chat_req.message,
                deep_search=chat_req.deep_search,
                deep_think=chat_req.deep_think,
            ):
                yield payload
        except Exception as e:
            error_payload = json.dumps({"event": "error", "message": str(e)})
            yield f"data: {error_payload}\n\n"

    headers = {"Cache-Control": "no-cache", "Connection": "keep-alive"}
    return StreamingResponse(event_generator(), media_type="text/event-stream", headers=headers)


@router.post("/messages/{message_id}/regenerate/stream")
async def regenerate_message_stream(
    message_id: int,
    chat_req: ChatRegenerateRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """regenerate_message_stream ?????"""
    message = await chat_crud.get_message(db, message_id)
    if not message:
        raise HTTPException(status_code=404, detail="Message not found")
    session = await chat_crud.get_session(db, message.session_id)
    if not session or session.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Message not found")
    if message.kb_id is not None:
        kb = await kb_crud.get_kb(db, message.kb_id)
        if not kb or kb.user_id != current_user.id:
            raise HTTPException(status_code=403, detail="无权访问该知识库")

    async def event_generator():
        """event_generator ?????"""
        try:
            async for payload in chat_service.stream_regenerate(
                db=db,
                user_id=current_user.id,
                message_id=message_id,
                deep_search=chat_req.deep_search,
                deep_think=chat_req.deep_think,
            ):
                yield payload
        except Exception as e:
            error_payload = json.dumps({"event": "error", "message": str(e)})
            yield f"data: {error_payload}\n\n"

    headers = {"Cache-Control": "no-cache", "Connection": "keep-alive"}
    return StreamingResponse(event_generator(), media_type="text/event-stream", headers=headers)


@router.get("/messages/{message_id}/debug", response_model=ChatPromptSnapshotResponse)
async def get_message_debug_snapshot(
    message_id: int,
    current_user: User = Depends(get_current_superuser),
    db: AsyncSession = Depends(get_db),
):
    """get_message_debug_snapshot ?????"""
    snapshot = await chat_prompt_snapshot_crud.get_by_message_id(db, message_id)
    if not snapshot:
        raise HTTPException(status_code=404, detail="Snapshot not found")
    return snapshot

@router.post("/knowledge", response_model=KnowledgeChatResponse)
async def chat_with_knowledge(
    req: KnowledgeChatRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    # 权限校验：使用 kb_crud.get_kb
    """chat_with_knowledge ?????"""
    kb = await kb_crud.get_kb(db, req.kb_id)
    if not kb or kb.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="无权访问该知识库")

    try:
        # 直接传整个 req 对象进去
        return await chat_service.handle_rag_chat(
            db=db,
            user_id=current_user.id,
            req=req
        )
    except Exception as e:
        logger.error(f"RAG Chat Error: {str(e)}")
        raise HTTPException(status_code=500, detail="生成回答失败")

@router.post("/knowledge/stream")
async def chat_with_knowledge_stream(
    req: KnowledgeChatRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """chat_with_knowledge_stream ?????"""
    kb = await kb_crud.get_kb(db, req.kb_id)
    if not kb or kb.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="无权访问该知识库")

    async def event_generator():
        """event_generator ?????"""
        try:
            async for payload in chat_service.stream_rag_chat(
                db=db,
                user_id=current_user.id,
                req=req
            ):
                yield payload
        except Exception as e:
            error_payload = json.dumps({"event": "error", "message": str(e)})
            yield f"data: {error_payload}\n\n"

    headers = {"Cache-Control": "no-cache", "Connection": "keep-alive"}
    return StreamingResponse(event_generator(), media_type="text/event-stream", headers=headers)
