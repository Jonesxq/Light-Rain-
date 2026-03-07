"""聊天额外功能模块（表情包、建议问题）"""

from typing import List, Optional

from langchain_core.messages import HumanMessage, SystemMessage
from sqlalchemy.ext.asyncio import AsyncSession

from app.constant.prompts import SUGGESTION_SYSTEM_PROMPT
from app.core.config.settings import settings
from app.core.logger import logger_manager
from app.crud.chat import chat_crud
from app.models.chat import ChatRole, ChatMessage
from app.services.usage import usage_service, UsageTimer
from app.tools.text_to_image import text_to_image
from app.utils.chat_meme import build_meme_caption
from app.utils.chat_suggestions import parse_suggestions
from app.utils.llm_factory import build_chat_llm
from app.utils.llm_usage import estimate_usage

logger = logger_manager.get_logger(__name__)


class ChatExtrasMixin:
    """聊天额外功能Mixin：提供表情包生成和后续问题建议功能"""

    async def generate_meme(
        self,
        db: AsyncSession,
        user_id: int,
        message_id: int,
    ) -> ChatMessage:
        """从助手消息生成表情包图片
        
        Args:
            db: 数据库会话
            user_id: 用户ID
            message_id: 消息ID
            
        Returns:
            包含表情包图片的ChatMessage对象
            
        Raises:
            ValueError: 当消息不存在、无权限或不是助手消息时
            RuntimeError: 当文生图失败时
        """
        message = await chat_crud.get_message(db, message_id)
        if not message:
            raise ValueError("Message not found")
        session = await chat_crud.get_session(db, message.session_id)
        if not session or session.user_id != user_id:
            raise ValueError("Message not found")
        if message.role != ChatRole.ASSISTANT:
            raise ValueError("Only assistant messages are supported")

        caption = build_meme_caption(message.content or "")
        prompt = (
            "网络表情包风格，夸张搞笑，简洁背景，高清，白色粗体描边中文文字："
            f"{caption}"
        )
        try:
            image_url = text_to_image.invoke({"prompt": prompt})
        except Exception:
            image_url = text_to_image.run(prompt)

        if not image_url or str(image_url).startswith("文生图失败"):
            raise RuntimeError(str(image_url) or "文生图失败")

        if isinstance(image_url, str) and "\n" in image_url:
            image_url = image_url.splitlines()[0].strip()

        content = f"![meme]({image_url})"
        ai_msg = await chat_crud.create_message(
            db,
            session_id=session.id,
            role="assistant",
            content=content,
            model_name=getattr(settings.llm, "TEXT_TO_IMAGE_MODEL", None),
            token_count=0,
        )
        await chat_crud.update_session_time(db, session.id)
        return ai_msg

    async def suggest_followups(
        self,
        db: AsyncSession,
        user_id: int,
        session_id: int,
        limit: int = 3,
        model: Optional[str] = None,
    ) -> List[str]:
        """根据最近聊天历史生成后续问题建议
        
        Args:
            db: 数据库会话
            user_id: 用户ID
            session_id: 会话ID
            limit: 建议问题数量（1-6）
            model: 使用的模型名称
            
        Returns:
            后续问题建议列表
        """
        limit = max(1, min(int(limit or 3), 6))
        messages = await chat_crud.get_session_messages(db, session_id)
        if not messages:
            return []

        filtered = [m for m in messages if m.role in (ChatRole.USER, ChatRole.ASSISTANT)]
        if len(filtered) < 2:
            return []

        recent = filtered[-12:]
        context_lines = []
        for msg in recent:
            content = (msg.content or "").strip()
            if not content:
                continue
            if len(content) > 200:
                content = content[:200] + "…"
            role_label = "用户" if msg.role == ChatRole.USER else "助手"
            context_lines.append(f"{role_label}: {content}")

        if len(context_lines) < 2:
            return []

        context_text = "\n".join(context_lines)
        resolved = await self._resolve_user_llm_config(db, user_id, model)
        llm = build_chat_llm(
            model=resolved["model"],
            api_key=resolved["api_key"],
            api_base_url=resolved["api_base_url"],
            temperature=0.7,
            streaming=False,
        )
        llm_messages = [
            SystemMessage(content=SUGGESTION_SYSTEM_PROMPT),
            HumanMessage(content=context_text),
        ]

        timer = UsageTimer()
        try:
            response = await llm.ainvoke(llm_messages)
            latency_ms = timer.stop_ms()
            usage = usage_service.extract_usage(response)
            if usage.get("total_tokens") is None:
                usage = estimate_usage(llm, llm_messages, getattr(response, "content", "") or "")
            cost_usd = usage_service.compute_cost(
                llm.model_name,
                usage.get("prompt_tokens"),
                usage.get("completion_tokens"),
            )
            await usage_service.record_event(
                db,
                user_id=user_id,
                event_type="chat_suggestions",
                model_name=llm.model_name,
                prompt_tokens=usage.get("prompt_tokens"),
                completion_tokens=usage.get("completion_tokens"),
                total_tokens=usage.get("total_tokens"),
                token_missing=bool(usage.get("token_missing")),
                latency_ms=latency_ms,
                cost_usd=cost_usd,
                success=True,
                metadata={"session_id": session_id},
            )
            raw = getattr(response, "content", "") or ""
            suggestions = parse_suggestions(raw)
            if not suggestions:
                return []
            return suggestions[:limit]
        except Exception as exc:
            try:
                latency_ms = timer.stop_ms()
            except Exception:
                latency_ms = None
            try:
                await usage_service.record_event(
                    db,
                    user_id=user_id,
                    event_type="chat_suggestions",
                    model_name=None,
                    prompt_tokens=None,
                    completion_tokens=None,
                    total_tokens=None,
                    token_missing=True,
                    latency_ms=latency_ms,
                    cost_usd=0.0,
                    success=False,
                    error_message=str(exc),
                    metadata={"session_id": session_id},
                )
            except Exception:
                pass
            logger.warning(f"Suggestion generation failed: {exc}")
            return []
