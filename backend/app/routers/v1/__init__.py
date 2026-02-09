"""API v1 路由聚合模块"""

from .auth import router as auth_router
from .users import router as user_router
from .chat import router as chat_router  # 聊天相关路由
from .knowledge import router as knowledge_router
from .llm_settings import router as llm_settings_router

# 对外导出所有 v1 路由
__all__ = ['auth_router', 'user_router','chat_router', 'knowledge_router', 'llm_settings_router']

