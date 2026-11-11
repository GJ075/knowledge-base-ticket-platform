"""Shared builders for unit tests (no database, no model service)."""

import uuid
from types import SimpleNamespace

import pytest

from app.services.retrieval import Origin, Retrieved


def make_document(title: str = "测试文档", doc_id=None):
    return SimpleNamespace(id=doc_id or uuid.uuid4(), title=title)


@pytest.fixture
def make_item():
    def _make(
        chunk_id: int = 1,
        *,
        content: str = "内容",
        chunk_index: int = 0,
        document=None,
        content_hash: str | None = None,
        token_count: int = 10,
        score: float = 0.0,
        origin: Origin = Origin.DENSE,
    ) -> Retrieved:
        return Retrieved(
            chunk_id=chunk_id,
            document=document or make_document(),
            content=content,
            heading_path=["文档", "章节"],
            chunk_index=chunk_index,
            content_hash=content_hash or f"hash-{chunk_id}",
            token_count=token_count,
            score=score,
            origin=origin,
        )

    return _make
