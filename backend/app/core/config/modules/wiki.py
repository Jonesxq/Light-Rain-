"""Wiki-RAG configuration module."""
from typing import Any

from pydantic import Field, field_validator

from app.core.config.base import EnvBaseSettings


class WikiSettings(EnvBaseSettings):
    """Wiki-RAG settings."""

    WIKI_RAG_ENABLED: bool = Field(default=True, description="Enable Wiki-RAG")
    WIKI_WRITEBACK_MODE: str = Field(
        default="manual",
        description="Wiki writeback mode",
    )
    WIKI_INGEST_MODE: str = Field(
        default="auto",
        description="Wiki ingest mode",
    )
    WIKI_ANSWER_CONFIDENCE_THRESHOLD: float = Field(
        default=0.72,
        description="Minimum confidence for Wiki answers",
    )
    WIKI_RETRIEVER_TOP_K: int = Field(
        default=5,
        description="Number of Wiki chunks to retrieve",
    )
    WIKI_STORAGE_DIR: str = Field(
        default="storage/wiki",
        description="Wiki storage directory",
    )
    WIKI_MAX_PAGE_CHARS: int = Field(
        default=12000,
        description="Maximum characters per Wiki page",
    )
    WIKI_PATCH_CONFIDENCE_THRESHOLD: float = Field(
        default=0.70,
        description="Minimum confidence for Wiki patch suggestions",
    )
    WIKI_AUTO_COMPILE_ON_INGEST: bool = Field(
        default=True,
        description="Compile Wiki pages automatically after ingest",
    )

    @field_validator("WIKI_WRITEBACK_MODE", mode="before")
    @classmethod
    def validate_writeback_mode(cls, value: Any) -> str:
        """Return the default writeback mode for unsupported values."""
        allowed_modes = {"manual", "auto_low_risk", "disabled"}
        if isinstance(value, str) and value in allowed_modes:
            return value
        return "manual"

    @field_validator("WIKI_INGEST_MODE", mode="before")
    @classmethod
    def validate_ingest_mode(cls, value: Any) -> str:
        """Return the default ingest mode for unsupported values."""
        allowed_modes = {"auto", "pending_review", "assisted"}
        if isinstance(value, str) and value in allowed_modes:
            return value
        return "auto"

    @field_validator("WIKI_ANSWER_CONFIDENCE_THRESHOLD", mode="before")
    @classmethod
    def validate_answer_confidence_threshold(cls, value: Any) -> float:
        """Return the default answer threshold when outside [0, 1]."""
        try:
            threshold = float(value)
        except (TypeError, ValueError):
            return 0.72
        if 0 <= threshold <= 1:
            return threshold
        return 0.72

    @field_validator("WIKI_RETRIEVER_TOP_K", mode="before")
    @classmethod
    def validate_retriever_top_k(cls, value: Any) -> int:
        """Return the default retriever size when outside 1..20."""
        try:
            top_k = int(value)
        except (TypeError, ValueError):
            return 5
        if 1 <= top_k <= 20:
            return top_k
        return 5

    @field_validator("WIKI_MAX_PAGE_CHARS", mode="before")
    @classmethod
    def validate_max_page_chars(cls, value: Any) -> int:
        """Return the default page size when outside 1000..200000."""
        try:
            max_chars = int(value)
        except (TypeError, ValueError):
            return 12000
        if 1000 <= max_chars <= 200000:
            return max_chars
        return 12000

    @field_validator("WIKI_PATCH_CONFIDENCE_THRESHOLD", mode="before")
    @classmethod
    def validate_patch_confidence_threshold(cls, value: Any) -> float:
        """Return the default patch threshold when outside [0, 1]."""
        try:
            threshold = float(value)
        except (TypeError, ValueError):
            return 0.70
        if 0 <= threshold <= 1:
            return threshold
        return 0.70
