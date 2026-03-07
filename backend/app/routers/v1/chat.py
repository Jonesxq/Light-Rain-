"""聊天API路由模块 - 提供会话管理、消息发送、附件上传等功能"""
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
    """构建附件预览文本
    
    清理文本中的换行符，截取指定长度并添加省略号
    
    Args:
        text: 原始文本内容
        max_len: 最大预览长度，默认200字符
        
    Returns:
        str: 格式化的预览文本
    """
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
    """创建新的聊天会话
    
    Args:
        session_data: 会话创建数据（包含标题）
        current_user: 当前登录用户
        db: 数据库会话
        
    Returns:
        ChatSessionResponse: 创建的会话信息
    """
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
    """获取当前用户的聊天会话列表
    
    支持分页、搜索和筛选已归档会话
    
    Args:
        skip: 跳过的记录数，用于分页
        limit: 返回的最大记录数，默认20
        q: 搜索关键词，用于搜索会话标题
        include_archived: 是否包含已归档的会话，默认False
        current_user: 当前登录用户
        db: 数据库会话
        
    Returns:
        List[ChatSessionResponse]: 会话列表
    """
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
    """更新聊天会话信息
    
    支持更新标题、置顶状态、归档状态和标签
    
    Args:
        session_id: 会话ID
        payload: 会话更新数据
        current_user: 当前登录用户
        db: 数据库会话
        
    Returns:
        ChatSessionResponse: 更新后的会话信息
        
    Raises:
        HTTPException: 会话不存在或无权限时返回404错误
    """
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
    """删除聊天会话
    
    Args:
        session_id: 会话ID
        current_user: 当前登录用户
        db: 数据库会话
        
    Raises:
        HTTPException: 会话不存在或无权限时返回404错误
    """
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
    """获取聊天后续问题建议
    
    基于当前会话内容，AI自动生成相关的后续问题
    
    Args:
        session_id: 会话ID
        payload: 建议请求参数（包含数量和模型）
        current_user: 当前登录用户
        db: 数据库会话
        
    Returns:
        ChatSuggestionResponse: 后续问题建议列表
        
    Raises:
        HTTPException: 会话不存在或无权限时返回404错误
    """
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
    """根据消息内容生成表情包
    
    Args:
        message_id: 消息ID
        current_user: 当前登录用户
        db: 数据库会话
        
    Returns:
        ChatMessageResponse: 包含表情包的消息
        
    Raises:
        HTTPException: 消息不存在时返回404，生成失败时返回502或500错误
    """
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
    """获取当前用户的附件列表
    
    返回所有上传的附件及其预览信息
    
    Args:
        current_user: 当前登录用户
        db: 数据库会话
        
    Returns:
        List[ChatAttachmentResponse]: 附件列表
    """
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
    """上传聊天附件
    
    支持PDF、DOCX、TXT、MD和图片格式，最大10MB
    
    Args:
        file: 上传的文件
        current_user: 当前登录用户
        db: 数据库会话
        
    Returns:
        ChatAttachmentResponse: 上传的附件信息
        
    Raises:
        HTTPException: 文件格式不支持时返回400，文件过大返回413，处理失败返回500
    """
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
    """删除附件
    
    同时删除数据库记录和本地文件
    
    Args:
        attachment_id: 附件ID
        current_user: 当前登录用户
        db: 数据库会话
        
    Returns:
        dict: 操作成功标识
        
    Raises:
        HTTPException: 附件不存在或无权限时返回404错误
    """
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
    """获取会话的历史消息
    
    Args:
        session_id: 会话ID
        current_user: 当前登录用户
        db: 数据库会话
        
    Returns:
        List[ChatMessageResponse]: 历史消息列表
        
    Raises:
        HTTPException: 会话不存在或无权限时返回404错误
    """
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
    """发送聊天消息（非流式）
    
    Args:
        session_id: 会话ID
        chat_req: 聊天请求数据（包含消息内容和配置）
        current_user: 当前登录用户
        db: 数据库会话
        
    Returns:
        ChatMessageResponse: AI回复消息
        
    Raises:
        HTTPException: 服务层错误返回502，其他错误返回500
    """
    try:
        ai_message = await chat_service.process_chat(
            db,
            current_user.id,
            session_id,
            chat_req
        )
        return ai_message
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Internal Chat Error")

@router.post("/sessions/{session_id}/stream")
async def stream_message(
        session_id: int,
        chat_req: ChatRequest,
        current_user: User = Depends(get_current_user),
        db: AsyncSession = Depends(get_db)
):
    """发送聊天消息（流式）
    
    使用Server-Sent Events实时推送AI回复内容
    
    Args:
        session_id: 会话ID
        chat_req: 聊天请求数据
        current_user: 当前登录用户
        db: 数据库会话
        
    Returns:
        StreamingResponse: SSE流式响应
        
    Raises:
        HTTPException: 会话不存在或无权限时返回404错误
    """
    session = await chat_crud.get_session(db, session_id)
    if not session or session.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Session not found")

    async def event_generator():
        """SSE事件生成器
        
        流式输出AI回复内容，出错时推送错误事件
        """
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
    """更新消息的收藏状态
    
    只能收藏助手的消息，不能收藏用户消息
    
    Args:
        message_id: 消息ID
        payload: 收藏状态更新数据
        current_user: 当前登录用户
        db: 数据库会话
        
    Returns:
        ChatMessageResponse: 更新后的消息
        
    Raises:
        HTTPException: 消息不存在时返回404，收藏用户消息返回400
    """
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
    """重新发送消息（流式）
    
    可以修改原始消息内容后重新发送，AI会生成新的回复
    
    Args:
        message_id: 要重新发送的消息ID
        chat_req: 聊天请求数据（可包含新的消息内容）
        current_user: 当前登录用户
        db: 数据库会话
        
    Returns:
        StreamingResponse: SSE流式响应
        
    Raises:
        HTTPException: 消息不存在时返回404，知识库无权限返回403
    """
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
        """SSE事件生成器 - 重发消息"""
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
    """重新生成AI回复（流式）
    
    使用相同的用户消息，让AI重新生成回复
    
    Args:
        message_id: 要重新生成的助手消息ID
        chat_req: 重新生成请求参数
        current_user: 当前登录用户
        db: 数据库会话
        
    Returns:
        StreamingResponse: SSE流式响应
        
    Raises:
        HTTPException: 消息不存在时返回404，知识库无权限返回403
    """
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
        """SSE事件生成器 - 重新生成回复"""
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
    """获取消息的调试快照（仅管理员）
    
    用于调试，查看发送给LLM的完整提示词快照
    
    Args:
        message_id: 消息ID
        current_user: 当前登录的超级用户
        db: 数据库会话
        
    Returns:
        ChatPromptSnapshotResponse: 提示词快照
        
    Raises:
        HTTPException: 快照不存在时返回404错误
    """
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
    """基于知识库进行RAG聊天（非流式）
    
    Args:
        req: RAG聊天请求（包含知识库ID和问题）
        current_user: 当前登录用户
        db: 数据库会话
        
    Returns:
        KnowledgeChatResponse: AI基于知识库的回答
        
    Raises:
        HTTPException: 知识库无权限返回403，生成失败返回500
    """
    kb = await kb_crud.get_kb(db, req.kb_id)
    if not kb or kb.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="无权访问该知识库")

    try:
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
    """基于知识库进行RAG聊天（流式）
    
    使用Server-Sent Events实时推送基于知识库的AI回答
    
    Args:
        req: RAG聊天请求
        current_user: 当前登录用户
        db: 数据库会话
        
    Returns:
        StreamingResponse: SSE流式响应
        
    Raises:
        HTTPException: 知识库无权限返回403
    """
    kb = await kb_crud.get_kb(db, req.kb_id)
    if not kb or kb.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="无权访问该知识库")

    async def event_generator():
        """SSE事件生成器 - RAG聊天"""
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
