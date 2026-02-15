"""services/chat.py."""

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
    """ChatService facade composed of mixins."""

    pass


chat_service = ChatService()
