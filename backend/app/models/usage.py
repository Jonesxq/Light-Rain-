"""models/usage.py."""
from datetime import datetime
from typing import Optional

from sqlalchemy import Column, ForeignKey, JSON, Numeric
from sqlmodel import Field, SQLModel


class UsageEvent(SQLModel, table=True):
    """UsageEvent ??"""
    __tablename__ = "usage_events"

    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int = Field(
        sa_column=Column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    )

    event_type: str = Field(max_length=50, index=True)
    model_name: Optional[str] = Field(default=None, max_length=100, index=True)

    prompt_tokens: Optional[int] = Field(default=None)
    completion_tokens: Optional[int] = Field(default=None)
    total_tokens: Optional[int] = Field(default=None)
    token_missing: bool = Field(default=False, index=True)

    latency_ms: Optional[int] = Field(default=None)
    cost_usd: float = Field(default=0.0, sa_column=Column(Numeric(12, 6)))

    success: bool = Field(default=True, index=True)
    error_message: Optional[str] = Field(default=None, max_length=500)

    event_metadata: Optional[dict] = Field(default=None, sa_column=Column("metadata", JSON))

    created_at: datetime = Field(default_factory=datetime.utcnow, index=True)


class UserUsageSettings(SQLModel, table=True):
    """UserUsageSettings ??"""
    __tablename__ = "user_usage_settings"

    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int = Field(
        sa_column=Column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, unique=True, index=True)
    )

    monthly_budget_usd: float = Field(default=0.0)
    daily_request_limit: int = Field(default=0)

    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
