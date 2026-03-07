"""网页搜索工具模块：提供网页内容抓取、HTML解析、搜索上下文构建等功能"""

from __future__ import annotations

import asyncio
import re
from typing import List

import httpx
from bs4 import BeautifulSoup


def strip_source_content(sources: List[dict]) -> List[dict]:
    """精简搜索源数据（移除大字段用于存储）
    
    Args:
        sources: 原始搜索源列表
        
    Returns:
        List[dict]: 精简后的搜索源列表，仅保留title、url、snippet、source_type
    """
    cleaned: List[dict] = []
    for item in sources or []:
        cleaned.append(
            {
                "title": item.get("title"),
                "url": item.get("url"),
                "snippet": item.get("snippet") or "",
                "source_type": item.get("source_type") or "web",
            }
        )
    return cleaned


def extract_html_text(html: str) -> str:
    """从HTML中提取可见文本
    
    移除script、style等标签，提取纯文本内容
    
    Args:
        html: HTML字符串
        
    Returns:
        str: 提取的纯文本
    """
    if not html:
        return ""
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()
    text = soup.get_text(separator=" ", strip=True)
    text = re.sub(r"\s+", " ", text).strip()
    return text


async def fetch_url_text(
    client: httpx.AsyncClient,
    url: str,
    max_chars: int = 4000,
) -> str:
    """抓取并提取单个URL的文本内容
    
    Args:
        client: HTTPX异步客户端
        url: 目标URL
        max_chars: 最大字符数限制，默认4000
        
    Returns:
        str: 提取的文本内容，失败返回空字符串
    """
    if not url:
        return ""
    try:
        resp = await client.get(url)
    except Exception:
        return ""
    if resp.status_code >= 400:
        return ""
    content_type = (resp.headers.get("content-type") or "").lower()
    if "text/html" in content_type:
        text = extract_html_text(resp.text)
    elif "text/plain" in content_type:
        text = re.sub(r"\s+", " ", resp.text or "").strip()
    else:
        return ""
    if not text:
        return ""
    if len(text) > max_chars:
        text = text[:max_chars] + "…"
    return text


async def fetch_web_sources(
    sources: List[dict],
    top_n: int = 4,
    timeout: float = 8.0,
) -> List[dict]:
    """抓取前N个搜索源并附加提取的内容
    
    Args:
        sources: 搜索源列表
        top_n: 抓取数量，默认4个
        timeout: 超时时间（秒），默认8秒
        
    Returns:
        List[dict]: 增强后的搜索源列表，包含提取的content字段
    """
    if not sources:
        return []
    target = sources[: max(0, top_n)]
    rest = sources[len(target):]
    headers = {
        "User-Agent": "Mozilla/5.0 (ChatClient) AppleWebKit/537.36 (KHTML, like Gecko)"
    }
    async with httpx.AsyncClient(timeout=timeout, headers=headers, follow_redirects=True) as client:
        tasks = [fetch_url_text(client, item.get("url", "")) for item in target]
        results = await asyncio.gather(*tasks, return_exceptions=True)
    merged: List[dict] = []
    for item, result in zip(target, results):
        enriched = dict(item)
        if isinstance(result, str) and result:
            enriched["content"] = result
        merged.append(enriched)
    merged.extend(rest)
    return merged


def build_search_context(sources: List[dict], max_len: int = 200) -> str:
    """构建索引式搜索上下文用于回答提示词
    
    Args:
        sources: 搜索源列表
        max_len: 每个片段的最大长度，默认200
        
    Returns:
        str: 格式化的搜索上下文字符串
    """
    if not sources:
        return ""
    lines: List[str] = []
    for idx, item in enumerate(sources, start=1):
        title = (item.get("title") or "网页来源").strip()
        snippet = (item.get("snippet") or "").strip()
        content = (item.get("content") or "").strip()
        if len(snippet) > max_len:
            snippet = snippet[:max_len] + "…"
        if len(content) > max_len:
            content = content[:max_len] + "…"
        url = (item.get("url") or "").strip()
        line = f"[{idx}] {title}"
        if snippet:
            line += f" - {snippet}"
        if content:
            line += f" 摘录：{content}"
        if url:
            line += f" ({url})"
        lines.append(line)
    return "\n".join(lines)
