"""schemas/news.py."""
from typing import List, Optional
from pydantic import BaseModel


class NewsItem(BaseModel):
    """NewsItem ??"""
    title: str
    link: str
    source: Optional[str] = None
    date: Optional[str] = None
    snippet: Optional[str] = None
    image_url: Optional[str] = None


class NewsListResponse(BaseModel):
    """NewsListResponse ??"""
    items: List[NewsItem]
    fetched_at: str
    from_cache: bool
