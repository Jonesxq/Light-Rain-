"""Web search helpers."""

from __future__ import annotations

import asyncio
import re
from typing import List

import httpx
from bs4 import BeautifulSoup


def strip_source_content(sources: List[dict]) -> List[dict]:
    """Remove heavy fields before storing sources."""
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
    """Extract visible text from HTML."""
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
    """Fetch and extract text from a single URL."""
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
    """Fetch top-N sources and attach extracted content."""
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
    """Build indexed context for answer prompt."""
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
