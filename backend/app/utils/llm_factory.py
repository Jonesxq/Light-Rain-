"""LLM工厂模块：用于构建聊天模型和嵌入模型实例"""
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
    """构建聊天大语言模型实例
    
    创建并配置ChatOpenAI模型，支持自定义模型、API密钥、API地址等参数
    
    Args:
        model: 模型名称，默认使用配置中的DEFAULT_MODEL
        api_key: API密钥，默认使用配置中的QWEN_API_KEY
        api_base_url: API基础地址，默认使用配置中的QWEN_BASE_URL
        temperature: 温度参数，控制输出的随机性，默认0.3
        streaming: 是否启用流式输出，默认False
        
    Returns:
        ChatOpenAI: 配置好的聊天模型实例
    """
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
    """构建文本嵌入模型实例
    
    创建并配置DashScopeEmbeddings模型，用于将文本转换为向量
    
    Args:
        model: 嵌入模型名称，默认使用配置中的EMBEDDING_MODEL
        api_key: API密钥，默认使用配置中的QWEN_API_KEY
        
    Returns:
        DashScopeEmbeddings: 配置好的嵌入模型实例
    """
    return DashScopeEmbeddings(
        model=model or settings.llm.EMBEDDING_MODEL,
        dashscope_api_key=api_key if api_key is not None else settings.llm.QWEN_API_KEY,
    )
