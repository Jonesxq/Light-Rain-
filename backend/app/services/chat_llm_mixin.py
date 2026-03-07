"""聊天服务的LLM配置辅助模块"""

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
    """LLM配置和构建器Mixin：提供LLM实例创建和用户配置解析功能"""

    def _get_llm(
        self,
        model_name: Optional[str] = None,
        streaming: bool = False,
        api_key: Optional[str] = None,
        api_base_url: Optional[str] = None,
        temperature: Optional[float] = None,
    ) -> ChatOpenAI:
        """构建LLM实例
        
        Args:
            model_name: 模型名称
            streaming: 是否启用流式输出
            api_key: API密钥
            api_base_url: API基础URL
            temperature: 温度参数（控制随机性）
            
        Returns:
            配置好的ChatOpenAI实例
        """
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
        """解析用户的LLM配置（优先使用用户自定义配置，回退到系统默认配置）
        
        Args:
            db: 数据库会话
            user_id: 用户ID
            request_model: 请求中指定的模型名称（覆盖用户配置）
            
        Returns:
            包含model、api_key、api_base_url的配置字典
            
        Raises:
            ValueError: 当用户API密钥解密失败时
        """
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
