"""聊天服务包入口。"""

from app.services.chat.service import ChatService

chat_service = ChatService()

__all__ = ["ChatService", "chat_service"]
