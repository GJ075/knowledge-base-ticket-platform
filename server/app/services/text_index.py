"""Text indexing helpers: Chinese segmentation for full-text search."""

from __future__ import annotations

import jieba

jieba.setLogLevel(20)


def segment_for_index(text: str) -> str:
    """Segment Chinese text into space separated tokens for tsvector."""
    if not text:
        return ""
    return " ".join(token for token in jieba.cut(text) if token.strip())
