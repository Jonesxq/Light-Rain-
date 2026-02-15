"""JSON parsing helpers."""

from __future__ import annotations

import json
import re
from typing import List, Optional


def parse_json_list(raw: str) -> List[str]:
    """Parse JSON list from model output, fallback to line split."""
    if not raw:
        return []
    text = raw.strip()
    if not text:
        return []
    items: List[str] = []
    try:
        data = json.loads(text)
        if isinstance(data, dict):
            data = data.get("queries") or data.get("items") or data.get("suggestions")
        if isinstance(data, list):
            items = [str(item) for item in data if item is not None]
        elif isinstance(data, str):
            items = [data]
    except Exception:
        try:
            match = re.search(r"\[[\s\S]*\]", text)
            if match:
                data = json.loads(match.group(0))
                if isinstance(data, list):
                    items = [str(item) for item in data if item is not None]
        except Exception:
            pass
    if not items:
        parts = re.split(r"[\r\n]+", text)
        for part in parts:
            if not part.strip():
                continue
            if "、" in part:
                items.extend([p for p in part.split("、") if p.strip()])
            elif ";" in part or "；" in part:
                items.extend([p for p in re.split(r"[；;]", part) if p.strip()])
            else:
                items.append(part)

    cleaned: List[str] = []
    seen = set()
    for item in items:
        q = str(item).strip().strip('"').strip("'")
        q = re.sub(r"^\s*(?:\d+[\.\)]|[-*•·])\s*", "", q)
        q = q.strip()
        if not q:
            continue
        key = q.lower()
        if key in seen:
            continue
        seen.add(key)
        cleaned.append(q)
    return cleaned


def parse_json_obj(raw: str) -> Optional[dict]:
    """Parse JSON object from model output."""
    if not raw:
        return None
    text = raw.strip()
    if not text:
        return None
    try:
        data = json.loads(text)
        if isinstance(data, dict):
            return data
        if isinstance(data, list):
            return {"steps": data}
    except Exception:
        try:
            match = re.search(r"\{[\s\S]*\}", text)
            if match:
                data = json.loads(match.group(0))
                if isinstance(data, dict):
                    return data
        except Exception:
            return None
    return None
