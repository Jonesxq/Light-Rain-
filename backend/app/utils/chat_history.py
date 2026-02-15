"""Chat history helpers."""

from __future__ import annotations

from typing import List

from langchain_core.messages import BaseMessage, HumanMessage, AIMessage, SystemMessage


def history_to_text(chat_history: List[BaseMessage], limit: int = 6) -> str:
    """Convert recent history to plain text for prompts."""
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
    """Serialize recent history to payload list."""
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
