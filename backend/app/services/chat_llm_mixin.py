"""LLM config helpers for chat service."""

from typing import Optional

from langchain_openai import ChatOpenAI
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config.settings import settings
from app.core.logger import logger_manager
from app.crud.llm_settings import llm_settings_crud
from app.utils.crypto import decrypt_text
from app.utils.llm_factory import build_chat_llm

logger = logger_manager.get_logger(__name__)


class ChatLLMMixin:
    """LLM config and builder helpers."""

    def _get_llm(
        self,
        model_name: Optional[str] = None,
        streaming: bool = False,
        api_key: Optional[str] = None,
        api_base_url: Optional[str] = None,
        temperature: Optional[float] = None,
    ) -> ChatOpenAI:
        """_get_llm ???"""
        return build_chat_llm(
            model=model_name,
            api_key=api_key,
            api_base_url=api_base_url,
            temperature=0.3 if temperature is None else temperature,
            streaming=streaming,
        )

    async def _resolve_user_llm_config(
        self,
        db: AsyncSession,
        user_id: int,
        request_model: Optional[str],
    ) -> dict:
        """_resolve_user_llm_config ?????"""
        model_override = (request_model or "").strip() or None

        settings_row = await llm_settings_crud.get_by_user_id(db, user_id)
        if not settings_row or not settings_row.enabled:
            return {
                "model": model_override or settings.llm.DEFAULT_MODEL,
                "api_key": settings.llm.QWEN_API_KEY,
                "api_base_url": settings.llm.QWEN_BASE_URL,
            }

        if not settings_row.api_key_encrypted:
            logger.warning("User LLM settings enabled but API key missing, fallback to system config.")
            return {
                "model": model_override or settings.llm.DEFAULT_MODEL,
                "api_key": settings.llm.QWEN_API_KEY,
                "api_base_url": settings.llm.QWEN_BASE_URL,
            }

        try:
            api_key = decrypt_text(settings_row.api_key_encrypted)
        except Exception as exc:
            logger.error(f"User LLM key decrypt failed: {exc}")
            raise ValueError("用户模型配置解密失败")

        model_name = model_override or settings_row.model or settings.llm.DEFAULT_MODEL
        api_base_url = settings_row.api_base_url or settings.llm.QWEN_BASE_URL
        return {
            "model": model_name,
            "api_key": api_key,
            "api_base_url": api_base_url,
        }
