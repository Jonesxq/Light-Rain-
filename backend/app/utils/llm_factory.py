"""utils/llm_factory.py."""
from typing import Optional

from langchain_community.embeddings import DashScopeEmbeddings
from langchain_openai import ChatOpenAI

from app.core.config.settings import settings


def build_chat_llm(
    model: Optional[str] = None,
    api_key: Optional[str] = None,
    api_base_url: Optional[str] = None,
    temperature: float = 0.3,
    streaming: bool = False,
) -> ChatOpenAI:
    """build_chat_llm ???"""
    return ChatOpenAI(
        model=model or settings.llm.DEFAULT_MODEL,
        openai_api_key=api_key if api_key is not None else settings.llm.QWEN_API_KEY,
        openai_api_base=api_base_url if api_base_url is not None else settings.llm.QWEN_BASE_URL,
        temperature=temperature,
        streaming=streaming,
    )


def build_embeddings(
    model: Optional[str] = None,
    api_key: Optional[str] = None,
) -> DashScopeEmbeddings:
    """build_embeddings ???"""
    return DashScopeEmbeddings(
        model=model or settings.llm.EMBEDDING_MODEL,
        dashscope_api_key=api_key if api_key is not None else settings.llm.QWEN_API_KEY,
    )
