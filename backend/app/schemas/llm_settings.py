"""LLM设置数据验证模型模块"""
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict


class LLMSettingsUpdate(BaseModel):
    """LLM设置更新模型"""
    enabled: Optional[bool] = None
    api_base_url: Optional[str] = None
    model: Optional[str] = None
    api_key: Optional[str] = None


class LLMSettingsResponse(BaseModel):
    """LLM设置响应模型"""
    enabled: bool = False
    api_base_url: Optional[str] = None
    model: Optional[str] = None
    api_key_masked: Optional[str] = None
    has_api_key: bool = False
    updated_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)
