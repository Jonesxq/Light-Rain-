"""聊天历史工具模块：提供聊天历史格式转换功能"""

from __future__ import annotations

from typing import List

from langchain_core.messages import BaseMessage, HumanMessage, AIMessage, SystemMessage


def history_to_text(chat_history: List[BaseMessage], limit: int = 6) -> str:
    """将聊天历史转换为纯文本格式（用于提示词）
    
    Args:
        chat_history: LangChain格式的聊天历史消息列表
        limit: 最近消息数量限制，默认6条
        
    Returns:
        str: 格式化的聊天历史文本，格式为"用户: xxx\n助手: xxx"
    """
    if not chat_history:
        return ""
    lines: list[str] = []
    for msg in chat_history[-limit:]:
        if isinstance(msg, HumanMessage):
            role = "用户"
        elif isinstance(msg, AIMessage):
            role = "助手"
        else:
            continue
        content = (msg.content or "").strip()
        if not content:
            continue
        lines.append(f"{role}: {content}")
    return "\n".join(lines)


def history_to_payload(chat_history: List[BaseMessage], limit: int = 10) -> List[dict]:
    """将聊天历史序列化为API载荷格式
    
    Args:
        chat_history: LangChain格式的聊天历史消息列表
        limit: 最近消息数量限制，默认10条
        
    Returns:
        List[dict]: 序列化后的消息列表，每条消息包含role和content字段
    """
    if not chat_history:
        return []
    payload: List[dict] = []
    for msg in chat_history[-limit:]:
        role = None
        if isinstance(msg, HumanMessage):
            role = "user"
        elif isinstance(msg, AIMessage):
            role = "assistant"
        elif isinstance(msg, SystemMessage):
            role = "system"
        if not role:
            continue
        content = (msg.content or "").strip()
        if not content:
            continue
        payload.append({"role": role, "content": content})
    return payload
