"""表情包文案生成工具模块：从对话内容生成短文案用于表情包生成"""

from __future__ import annotations

import re


def build_meme_caption(content: str) -> str:
    """从对话内容构建表情包短文案
    
    清理Markdown格式（代码块、图片、引用、列表等）并截取前50个字符
    
    Args:
        content: 原始对话内容
        
    Returns:
        str: 清理后的短文案，默认返回"今天的我"
    """
    text = (content or "").strip()
    if not text:
        return "今天的我"
    # Remove fenced code blocks
    text = re.sub(r"```[\s\S]*?```", "", text)
    # Remove markdown images
    text = re.sub(r"!\[[^\]]*\]\([^)]+\)", "", text)
    # Remove blockquote prefix
    text = re.sub(r"^\s*>\s?", "", text, flags=re.MULTILINE)
    # Remove list prefixes
    text = re.sub(r"^\s*[-*•·]\s+", "", text, flags=re.MULTILINE)
    # Collapse whitespace
    text = re.sub(r"\s+", " ", text).strip()
    if not text:
        return "今天的我"
    if len(text) > 50:
        text = text[:50]
    return text
