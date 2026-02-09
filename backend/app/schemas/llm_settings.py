"""Schemas for user LLM settings."""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict


class LLMSettingsUpdate(BaseModel):
    enabled: Optional[bool] = None
    api_base_url: Optional[str] = None
    model: Optional[str] = None
    api_key: Optional[str] = None


class LLMSettingsResponse(BaseModel):
    enabled: bool = False
    api_base_url: Optional[str] = None
    model: Optional[str] = None
    api_key_masked: Optional[str] = None
    has_api_key: bool = False
    updated_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)
