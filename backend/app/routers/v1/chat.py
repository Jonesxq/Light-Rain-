"""聊天接口：会话管理、普通聊天、知识库问答"""
import json
from typing import List
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import get_current_user
from app.crud.knowledge import kb_crud
from app.models.user import User
from app.models.chat import ChatRole
from app.schemas.chat import (
    ChatSessionResponse,
    ChatSessionCreate,
    ChatMessageResponse,
    ChatRequest, KnowledgeChatRequest, KnowledgeChatResponse
)
from app.core.logger import logger_manager
from app.crud.chat import chat_crud
from app.services.chat import chat_service
from app.services.knowledge import kb_service



logger = logger_manager.get_logger(__name__)
router = APIRouter(prefix="/chat", tags=["Chat"])

@router.post("/sessions", response_model=ChatSessionResponse)
async def create_session(
    session_data: ChatSessionCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """创建会话"""
    return await chat_crud.create_session(db, current_user.id, session_data.title)

@router.get("/sessions", response_model=List[ChatSessionResponse])
async def get_my_sessions(
    skip: int = 0,
    limit: int = 20,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """获取当前用户会话列表"""
    return await chat_crud.get_user_sessions(db, current_user.id, skip, limit)

@router.delete("/sessions/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_session(
    session_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """删除会话（软删除）"""
    success = await chat_crud.delete_session(db, session_id, current_user.id)
    if not success:
        raise HTTPException(status_code=404, detail="Session not found")

# ========== 聊天交互 ==========

@router.get("/sessions/{session_id}/messages", response_model=List[ChatMessageResponse])
async def get_history(
        session_id: int,
        current_user: User = Depends(get_current_user),
        db: AsyncSession = Depends(get_db)
):
    """获取历史消息（当前会话全部消息）"""
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
    """发送消息（非流式）"""
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
    """发送消息（流式 SSE，前端当前默认不使用）"""
    session = await chat_crud.get_session(db, session_id)
    if not session or session.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Session not found")

    async def event_generator():
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

@router.post("/knowledge", response_model=KnowledgeChatResponse)
async def chat_with_knowledge(
    req: KnowledgeChatRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """知识库问答（非流式）"""
    # 权限校验：使用 kb_crud.get_kb
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
    """知识库问答（流式 SSE，前端当前默认不使用）"""
    kb = await kb_crud.get_kb(db, req.kb_id)
    if not kb or kb.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="无权访问该知识库")

    async def event_generator():
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
