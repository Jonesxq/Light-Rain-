"""Suggestion parsing helpers."""

from __future__ import annotations

import re
from typing import List, Optional

from app.utils.json_utils import parse_json_list


def clean_suggestion_text(text: str) -> Optional[str]:
    """Normalize a suggestion string."""
    if not text:
        return None
    cleaned = text.strip().strip('"').strip("'")
    cleaned = re.sub(r"^\s*(?:\d+[\.\)]|[-*•·]|[（(]?\d+[)）]?\s*[、.])\s*", "", cleaned)
    cleaned = re.sub(r"^(?:建议|你可能要问|可以问)[:：]\s*", "", cleaned)
    cleaned = cleaned.strip()
    if not cleaned:
        return None
    if len(cleaned) > 20:
        cleaned = cleaned[:20]
    return cleaned


def parse_suggestions(raw: str, limit: Optional[int] = None) -> List[str]:
    """Parse suggestions from model output."""
    if not raw:
        return []
    text = raw.strip()
    if not text:
        return []
    items = parse_json_list(text)
    if not items:
        return []

    cleaned_list: List[str] = []
    seen = set()
    for item in items:
        cleaned = clean_suggestion_text(str(item))
        if not cleaned:
            continue
        key = cleaned.lower()
        if key in seen:
            continue
        seen.add(key)
        cleaned_list.append(cleaned)
    if limit is not None:
        return cleaned_list[:limit]
    return cleaned_list
