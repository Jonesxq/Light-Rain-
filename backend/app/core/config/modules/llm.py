"""大语言模型配置模块"""
from typing import Optional

from pydantic import Field
from app.core.config.base import EnvBaseSettings


class LLMSettings(EnvBaseSettings):
    """大语言模型设置类（阿里云通义千问/DashScope）"""

    # 阿里云 DashScope API Key
    QWEN_API_KEY: str = Field(
        default="",
        description="DashScope API密钥")

    # 用户自定义 LLM API Key 加密密钥（Fernet，urlsafe base64）
    USER_LLM_KEY_ENCRYPTION_KEY: str = Field(
        default="",
        description="用于加密用户LLM API密钥的Fernet密钥"
    )

    # DashScope 兼容 OpenAI 的 Base URL
    QWEN_BASE_URL: str = Field(
        default="https://dashscope.aliyuncs.com/compatible-mode/v1",
        description="DashScope基础URL"
    )

    # 天气工具 API Key（WeatherAPI）
    WEATHER_API_KEY: str = Field(
        default="",
        description="天气API密钥"
    )

    # 联网搜索 API Key（Serper）
    SERPER_API_KEY: str = Field(
        default="",
        description="联网搜索API密钥"
    )

    # 文生图模型配置（DashScope）
    TEXT_TO_IMAGE_MODEL: str = Field(
        default="qwen-image-plus",
        description="文生图模型"
    )
    TEXT_TO_IMAGE_SIZE: str = Field(
        default="1024*1024",
        description="文生图尺寸"
    )

    # 默认模型 (如果你有 qwen3-max 权限，在这里配置默认值，或者用 qwen-max)
    DEFAULT_MODEL: str = Field(default="qwen3.7-max", description="默认大语言模型")
    # 查询改写模型（用于 RAG 问题重写）
    QUERY_REWRITE_MODEL: str = Field(default="qwen3.7-max", description="查询改写模型")

    # Embedding 模型配置
    # 通义千问推荐使用: text-embedding-v1
    EMBEDDING_MODEL: str = Field(default="text-embedding-v1", description="嵌入模型")

    # RAG 检索配置
    # 重排序模型（DashScope）
    RERANK_MODEL: str = Field(default="gte-rerank-v2", description="重排序模型")
    # RAG 相关度阈值（重排得分低于此值将被丢弃）
    RAG_RELEVANCE_THRESHOLD: float = Field(default=0.01, description="RAG相关度阈值")
    # BM25 初筛候选数
    RAG_BM25_TOP_K: int = Field(default=50, description="BM25初筛候选数量")
    # 语义检索保留数（在 BM25 候选内做向量检索）
    RAG_SEMANTIC_TOP_K: int = Field(default=20, description="语义检索保留数量")
    # 最终返回给 LLM 的知识片段数量
    RAG_FINAL_TOP_K: int = Field(default=3, description="最终返回给LLM的知识片段数量")
    # BM25 缓存 TTL（秒）
    RAG_BM25_CACHE_TTL: int = Field(default=600, description="BM25缓存过期时间（秒）")
    # chunk 摘要最大字符数（用于向量入库）
    RAG_SUMMARY_MAX_CHARS: int = Field(default=180, description="块摘要最大字符数")
    # chunk 摘要并发度
    RAG_SUMMARY_CONCURRENCY: int = Field(default=5, description="块摘要并发度")
    # 超过该 chunk 数时跳过 LLM 摘要，避免超大 PDF 入库耗时和成本失控；0 表示全部跳过
    RAG_SUMMARY_MAX_CHUNKS: int = Field(default=400, description="启用块摘要的最大 chunk 数")
    # 通用分块参数
    RAG_CHUNK_SIZE_DEFAULT: int = Field(default=600, description="默认分块大小")
    RAG_CHUNK_OVERLAP_DEFAULT: int = Field(default=60, description="默认分块重叠大小")
    # 按文件类型分块调优（None 表示继承默认值）
    RAG_CHUNK_SIZE_PDF: Optional[int] = Field(default=None, description="PDF分块大小")
    RAG_CHUNK_OVERLAP_PDF: Optional[int] = Field(default=None, description="PDF分块重叠大小")
    RAG_CHUNK_SIZE_DOCX: Optional[int] = Field(default=None, description="DOCX分块大小")
    RAG_CHUNK_OVERLAP_DOCX: Optional[int] = Field(default=None, description="DOCX分块重叠大小")
    RAG_CHUNK_SIZE_MD: Optional[int] = Field(default=None, description="Markdown分块大小")
    RAG_CHUNK_OVERLAP_MD: Optional[int] = Field(default=None, description="Markdown分块重叠大小")
    RAG_CHUNK_SIZE_TXT: Optional[int] = Field(default=1500, description="TXT分块大小")
    RAG_CHUNK_OVERLAP_TXT: Optional[int] = Field(default=150, description="TXT分块重叠大小")
    RAG_CHUNK_SIZE_PPTX: Optional[int] = Field(default=None, description="PPTX分块大小")
    RAG_CHUNK_OVERLAP_PPTX: Optional[int] = Field(default=None, description="PPTX分块重叠大小")

    MILVUS_COLLECTION_PREFIX: str = "kb_"
    MILVUS_URI: str = Field(default="tcp://localhost:19530", description="Milvus连接URI")
    # 如果是本地简单的 Milvus，user 和 password 可以为空
    MILVUS_USER: Optional[str] = Field(default=None, description="Milvus用户名")
    MILVUS_PASSWORD: Optional[str] = Field(default=None, description="Milvus密码")
