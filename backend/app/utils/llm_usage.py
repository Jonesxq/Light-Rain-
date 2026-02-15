"""LLM usage estimation helpers."""

from __future__ import annotations

import math
import re
from typing import List

from langchain_core.messages import BaseMessage
from langchain_openai import ChatOpenAI


def rough_token_count(text: str) -> int:
    """Rough token estimate when provider usage is missing."""
    if not text:
        return 0
    # If CJK is present, count characters; otherwise approximate 4 chars per token.
    if re.search(r"[\u4e00-\u9fff]", text):
        return len(text)
    return max(1, math.ceil(len(text) / 4))


def estimate_usage(
    llm: ChatOpenAI,
    messages: List[BaseMessage],
    output_text: str,
) -> dict:
    """Estimate token usage when provider doesn't return usage metadata."""
    prompt_tokens = None
    completion_tokens = None

    try:
        prompt_tokens = llm.get_num_tokens_from_messages(messages)
    except Exception:
        # Fallback to rough count of concatenated prompt text.
        prompt_text = "".join([getattr(m, "content", "") or "" for m in messages])
        prompt_tokens = rough_token_count(prompt_text)

    try:
        completion_tokens = llm.get_num_tokens(output_text or "")
    except Exception:
        completion_tokens = rough_token_count(output_text or "")

    total_tokens = (prompt_tokens or 0) + (completion_tokens or 0)
    token_missing = total_tokens == 0 and (prompt_tokens or 0) == 0 and (completion_tokens or 0) == 0

    return {
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "total_tokens": total_tokens,
        "token_missing": token_missing,
    }
