"""routers/v1/news.py."""
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import get_current_user
from app.models.user import User
from app.schemas.news import NewsListResponse
from app.core.config.settings import settings
from app.services.ai_news import ai_news_service

router = APIRouter(prefix="/news", tags=["AI News"])


@router.get("/ai/latest", response_model=NewsListResponse)
async def get_ai_latest_news(
    limit: int = Query(settings.news.AI_NEWS_DEFAULT_LIMIT, ge=1, le=20),
    refresh: int = Query(0, ge=0, le=1),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """get_ai_latest_news ?????"""
    _ = current_user
    _ = db
    payload = await ai_news_service.get_latest(limit=limit, refresh=bool(refresh))
    return payload
