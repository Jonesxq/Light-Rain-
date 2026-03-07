"""AI新闻服务：获取最新AI相关新闻"""
from __future__ import annotations

import asyncio
import hashlib
import json
from datetime import datetime, timezone
from typing import Any

from fastapi import HTTPException
from langchain_community.utilities import GoogleSerperAPIWrapper

from app.core.config.settings import settings
from app.core.logger import logger_manager
from app.core.redis import redis_manager

logger = logger_manager.get_logger(__name__)


class AiNewsService:
    """AI新闻服务：通过Serper API获取AI相关新闻"""
    
    def _build_wrapper(self, k: int) -> GoogleSerperAPIWrapper:
        """构建Serper API包装器
        
        Args:
            k: 返回的结果数量
            
        Returns:
            Serper API包装器实例
        """
        return GoogleSerperAPIWrapper(
            serper_api_key=settings.llm.SERPER_API_KEY,
            type="news",
            gl=settings.news.AI_NEWS_GL,
            hl=settings.news.AI_NEWS_HL,
            k=k,
            tbs=settings.news.AI_NEWS_TBS,
        )

    def _cache_key(self, limit: int, query: str) -> str:
        """生成缓存键
        
        Args:
            limit: 结果数量限制
            query: 查询关键词
            
        Returns:
            缓存键字符串
        """
        query_hash = hashlib.sha1(query.encode("utf-8")).hexdigest()[:12]
        return (
            f"news:ai:{settings.news.AI_NEWS_GL}:"
            f"{settings.news.AI_NEWS_HL}:{settings.news.AI_NEWS_TBS}:"
            f"{limit}:{query_hash}"
        )

    def _clean_items(self, raw_items: list[dict[str, Any]], limit: int) -> list[dict[str, Any]]:
        """清理并标准化新闻项
        
        Args:
            raw_items: 原始新闻项列表
            limit: 结果数量限制
            
        Returns:
            标准化后的新闻项列表
        """
        cleaned: list[dict[str, Any]] = []
        seen_links: set[str] = set()
        for item in raw_items:
            if not isinstance(item, dict):
                continue
            link = (item.get("link") or item.get("url") or "").strip()
            title = (item.get("title") or item.get("name") or "").strip()
            if not link or not title:
                continue
            if link in seen_links:
                continue
            seen_links.add(link)
            cleaned.append(
                {
                    "title": title,
                    "link": link,
                    "source": item.get("source") or item.get("publisher") or "",
                    "date": item.get("date") or item.get("publishedAt") or "",
                    "snippet": item.get("snippet") or item.get("description") or "",
                    "image_url": item.get("imageUrl") or item.get("image") or item.get("thumbnail") or "",
                }
            )
            if len(cleaned) >= limit:
                break
        return cleaned

    async def get_latest(self, limit: int, refresh: bool) -> dict:
        """获取最新AI新闻
        
        Args:
            limit: 返回的新闻数量
            refresh: 是否强制刷新缓存
            
        Returns:
            包含新闻列表和元数据的字典
            
        Raises:
            HTTPException: 当SERPER_API_KEY未配置时
        """
        if not settings.llm.SERPER_API_KEY:
            raise HTTPException(status_code=503, detail="SERPER_API_KEY 未配置")

        # 限制结果数量在1-20之间
        safe_limit = max(1, min(int(limit), 20))
        query = settings.news.AI_NEWS_QUERY
        cache_key = self._cache_key(safe_limit, query)

        # 尝试从缓存读取
        if not refresh:
            try:
                cached = await redis_manager.get_async(cache_key)
                if cached:
                    payload = json.loads(cached)
                    payload["from_cache"] = True
                    return payload
            except Exception as exc:
                logger.warning(f"AI news cache read failed: {exc}")

        # 从Serper API获取新闻
        wrapper = self._build_wrapper(max(safe_limit * 2, 10))
        results = await asyncio.to_thread(wrapper.results, query)
        raw_items = results.get("news") if isinstance(results, dict) else []
        raw_items = raw_items if isinstance(raw_items, list) else []

        # 清理和标准化新闻项
        items = self._clean_items(raw_items, safe_limit)
        fetched_at = datetime.now(timezone.utc).isoformat()
        payload = {
            "items": items,
            "fetched_at": fetched_at,
            "from_cache": False,
        }

        # 写入缓存
        try:
            await redis_manager.set_async(
                cache_key,
                json.dumps(payload, ensure_ascii=False),
                ex=int(settings.news.AI_NEWS_CACHE_TTL_SECONDS),
            )
        except Exception as exc:
            logger.warning(f"AI news cache write failed: {exc}")

        return payload


# 全局服务实例
ai_news_service = AiNewsService()
