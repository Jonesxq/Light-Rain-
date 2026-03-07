"""建议解析工具模块：从模型输出中解析和清理建议问题列表"""

from __future__ import annotations

import re
from typing import List, Optional

from app.utils.json_utils import parse_json_list


def clean_suggestion_text(text: str) -> Optional[str]:
    """清理并规范化建议文本
    
    移除序号、前缀、引号等，并截取前20个字符
    
    Args:
        text: 原始建议文本
        
    Returns:
        Optional[str]: 清理后的文本，无效时返回None
    """
    if not text:
        return None
    cleaned = text.strip().strip('"').strip("'")
    cleaned = re.sub(r"^\s*(?:\d+[\.\)]|[-*•·]|[（(]?\d+[)）]?\s*[、.])\s*", "", cleaned)
    cleaned = re.sub(r"^(?:建议|你可能要问|可以问)[:：]\s*", "", cleaned)
    cleaned = cleaned.strip()
    if not cleaned:
        return None
    if len(cleaned) > 20:
        cleaned = cleaned[:20]
    return cleaned


def parse_suggestions(raw: str, limit: Optional[int] = None) -> List[str]:
    """从模型输出中解析建议列表
    
    支持JSON格式和多种文本格式，自动去重和清理
    
    Args:
        raw: 模型原始输出
        limit: 返回数量限制，可选
        
    Returns:
        List[str]: 解析后的建议列表
    """
    if not raw:
        return []
    text = raw.strip()
    if not text:
        return []
    items = parse_json_list(text)
    if not items:
        return []

    cleaned_list: List[str] = []
    seen = set()
    for item in items:
        cleaned = clean_suggestion_text(str(item))
        if not cleaned:
            continue
        key = cleaned.lower()
        if key in seen:
            continue
        seen.add(key)
        cleaned_list.append(cleaned)
    if limit is not None:
        return cleaned_list[:limit]
    return cleaned_list
