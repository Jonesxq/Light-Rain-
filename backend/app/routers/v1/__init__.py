
"""API v1 路由模块 - 包含所有v1版本的API端点"""
from .auth import router as auth_router
from .users import router as user_router
from .chat import router as chat_router  # 聊天相关路由
from .knowledge import router as knowledge_router
from .llm_settings import router as llm_settings_router
from .usage import router as usage_router
from .news import router as news_router
from .wiki import router as wiki_router

# 对外导出所有 v1 路由
__all__ = [
    'auth_router',
    'user_router',
    'chat_router',
    'knowledge_router',
    'llm_settings_router',
    'usage_router',
    'news_router',
    'wiki_router',
]
