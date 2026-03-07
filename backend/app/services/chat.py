"""聊天服务模块"""

from app.services.chat_context_mixin import ChatContextMixin
from app.services.chat_deep_search_mixin import ChatDeepSearchMixin
from app.services.chat_deep_think_mixin import ChatDeepThinkMixin
from app.services.chat_entry_mixin import ChatEntryMixin
from app.services.chat_extras_mixin import ChatExtrasMixin
from app.services.chat_llm_mixin import ChatLLMMixin
from app.services.chat_rag_mixin import ChatRagMixin
from app.services.chat_tool_mixin import ChatToolMixin


class ChatService(
    ChatEntryMixin,
    ChatRagMixin,
    ChatDeepSearchMixin,
    ChatDeepThinkMixin,
    ChatToolMixin,
    ChatContextMixin,
    ChatLLMMixin,
    ChatExtrasMixin,
):
    """聊天服务门面类：由多个Mixin组合而成，提供完整的聊天功能
    
    功能包括：
    - 普通聊天（支持工具调用）
    - 知识库问答（RAG）
    - 联网搜索（深度搜索）
    - 深度思考（推理）
    - 上下文管理
    - 流式输出
    - 消息编辑与重生成
    """

    pass


chat_service = ChatService()
