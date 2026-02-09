"""LLM configuration module"""
from typing import Optional

from pydantic import Field
from app.core.config.base import EnvBaseSettings


class LLMSettings(EnvBaseSettings):
    """LLM Configuration (DashScope/Qwen)"""

    # 阿里云 DashScope API Key
    QWEN_API_KEY: str = Field(
        default="",
        description="DashScope API Key")

    # 用户自定义 LLM API Key 加密密钥（Fernet，urlsafe base64）
    USER_LLM_KEY_ENCRYPTION_KEY: str = Field(
        default="",
        description="Fernet key for encrypting user LLM API keys"
    )

    # DashScope 兼容 OpenAI 的 Base URL
    QWEN_BASE_URL: str = Field(
        default="https://dashscope.aliyuncs.com/compatible-mode/v1",
        description="DashScope Base URL"
    )

    # 天气工具 API Key（WeatherAPI）
    WEATHER_API_KEY: str = Field(
        default="",
        description="WeatherAPI Key"
    )

    # 联网搜索 API Key（Serper）
    SERPER_API_KEY: str = Field(
        default="",
        description="Serper API Key"
    )

    # 文生图模型配置（DashScope）
    TEXT_TO_IMAGE_MODEL: str = Field(
        default="qwen-image-plus",
        description="Text-to-image model"
    )
    TEXT_TO_IMAGE_SIZE: str = Field(
        default="1024*1024",
        description="Text-to-image size"
    )

    # 默认模型 (如果你有 qwen3-max 权限，在这里配置默认值，或者用 qwen-max)
    DEFAULT_MODEL: str = Field(default="qwen3-max", description="Default LLM Model")
    # 查询改写模型（用于 RAG 问题重写）
    QUERY_REWRITE_MODEL: str = Field(default="qwen-max", description="Query rewrite model")

    # Embedding 模型配置
    # 通义千问推荐使用: text-embedding-v1
    EMBEDDING_MODEL: str = Field(default="text-embedding-v1")

    # RAG 检索配置
    # 重排序模型（DashScope）
    RERANK_MODEL: str = Field(default="gte-rerank-v2")
    # BM25 初筛候选数
    RAG_BM25_TOP_K: int = Field(default=50)
    # 语义检索保留数（在 BM25 候选内做向量检索）
    RAG_SEMANTIC_TOP_K: int = Field(default=20)
    # BM25 缓存 TTL（秒）
    RAG_BM25_CACHE_TTL: int = Field(default=600)  # seconds
    # chunk 摘要最大字符数（用于向量入库）
    RAG_SUMMARY_MAX_CHARS: int = Field(default=180)
    # chunk 摘要并发度
    RAG_SUMMARY_CONCURRENCY: int = Field(default=5)
    # 通用分块参数
    RAG_CHUNK_SIZE_DEFAULT: int = Field(default=600)
    RAG_CHUNK_OVERLAP_DEFAULT: int = Field(default=60)
    # 按文件类型分块调优（None 表示继承默认值）
    RAG_CHUNK_SIZE_PDF: Optional[int] = Field(default=None)
    RAG_CHUNK_OVERLAP_PDF: Optional[int] = Field(default=None)
    RAG_CHUNK_SIZE_DOCX: Optional[int] = Field(default=None)
    RAG_CHUNK_OVERLAP_DOCX: Optional[int] = Field(default=None)
    RAG_CHUNK_SIZE_MD: Optional[int] = Field(default=None)
    RAG_CHUNK_OVERLAP_MD: Optional[int] = Field(default=None)
    RAG_CHUNK_SIZE_TXT: Optional[int] = Field(default=None)
    RAG_CHUNK_OVERLAP_TXT: Optional[int] = Field(default=None)
    RAG_CHUNK_SIZE_PPTX: Optional[int] = Field(default=None)
    RAG_CHUNK_OVERLAP_PPTX: Optional[int] = Field(default=None)

    MILVUS_COLLECTION_PREFIX: str = "kb_"
    MILVUS_URI: str = Field(default="http://localhost:19530")
    # 如果是本地简单的 Milvus，user 和 password 可以为空
    MILVUS_USER: Optional[str] = None
    MILVUS_PASSWORD: Optional[str] = None
