"""LLM使用量估算工具模块：当提供商不返回使用元数据时估算token使用量"""

from __future__ import annotations

import math
import re
from typing import List

from langchain_core.messages import BaseMessage
from langchain_openai import ChatOpenAI


def rough_token_count(text: str) -> int:
    """粗略估算token数量（当提供商不返回使用量时）
    
    包含中文时按字符数计算，否则按每4个字符1个token估算
    
    Args:
        text: 待估算的文本
        
    Returns:
        int: 估算的token数量
    """
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
    """估算token使用量（当提供商不返回使用元数据时）
    
    优先使用模型内置的token计数方法，失败时降级到粗略估算
    
    Args:
        llm: ChatOpenAI模型实例
        messages: 输入消息列表
        output_text: 模型输出文本
        
    Returns:
        dict: 包含prompt_tokens、completion_tokens、total_tokens、token_missing的字典
    """
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
