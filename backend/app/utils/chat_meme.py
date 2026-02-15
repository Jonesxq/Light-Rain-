"""Meme caption helpers."""

from __future__ import annotations

import re


def build_meme_caption(content: str) -> str:
    """Build short caption text for meme generation."""
    text = (content or "").strip()
    if not text:
        return "今天的我"
    # Remove fenced code blocks
    text = re.sub(r"```[\s\S]*?```", "", text)
    # Remove markdown images
    text = re.sub(r"!\[[^\]]*\]\([^)]+\)", "", text)
    # Remove blockquote prefix
    text = re.sub(r"^\s*>\s?", "", text, flags=re.MULTILINE)
    # Remove list prefixes
    text = re.sub(r"^\s*[-*•·]\s+", "", text, flags=re.MULTILINE)
    # Collapse whitespace
    text = re.sub(r"\s+", " ", text).strip()
    if not text:
        return "今天的我"
    if len(text) > 50:
        text = text[:50]
    return text
