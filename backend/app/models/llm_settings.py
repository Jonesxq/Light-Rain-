
"""models/llm_settings.py."""
from datetime import datetime
from typing import Optional

from sqlalchemy import Column, ForeignKey, Text
from sqlmodel import Field, SQLModel


class UserLLMSettings(SQLModel, table=True):
    """UserLLMSettings ??"""
    __tablename__ = "user_llm_settings"

    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int = Field(
        sa_column=Column(
            ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
            unique=True,
            index=True,
        )
    )

    api_key_encrypted: Optional[str] = Field(default=None, sa_column=Column(Text))
    api_key_last4: Optional[str] = Field(default=None, max_length=10)
    api_base_url: Optional[str] = Field(default=None, max_length=255)
    model: Optional[str] = Field(default=None, max_length=100)

    enabled: bool = Field(default=True)

    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
