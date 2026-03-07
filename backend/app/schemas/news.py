"""新闻数据验证模型模块 - 新闻列表和新闻项的响应模型"""
from typing import List, Optional
from pydantic import BaseModel


class NewsItem(BaseModel):
    """新闻项模型 - 单条新闻的信息"""
    title: str
    link: str
    source: Optional[str] = None
    date: Optional[str] = None
    snippet: Optional[str] = None
    image_url: Optional[str] = None


class NewsListResponse(BaseModel):
    """新闻列表响应模型 - 返回新闻列表和获取信息"""
    items: List[NewsItem]
    fetched_at: str
    from_cache: bool
