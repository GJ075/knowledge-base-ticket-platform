"""Unified retrieval pipeline: dense recall, hybrid fusion, rerank, assembly.

Retrieved items hold plain values copied from the ORM chunk. Assembly steps
merge and renumber items, so they must never mutate persisted entities.
"""

from __future__ import annotations

import logging
from dataclasses import asdict, dataclass
from enum import Enum

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models.document import Document, DocumentChunk
from app.services.embedding_client import embed_query, rerank_pairs
from app.services.text_index import segment_for_index

RRF_K = 60
MERGE_MAX_CHARS = 1200

logger = logging.getLogger("app")


class Origin(str, Enum):
    DENSE = "dense"
    SPARSE = "sparse"
    FUSED = "fused"
    RERANK = "rerank"


@dataclass
class RetrievalConfig:
    candidate_k: int = 30
    fused_k: int = 40
    final_k: int = 5
    hybrid_enabled: bool = False
    rerank_enabled: bool = False
    rerank_top_n: int = 40
    rerank_threshold: float = 0.0
    rerank_delta: float = 0.0
    rewrite_enabled: bool = False
    context_token_budget: int = 3000

    def __post_init__(self) -> None:
        if min(self.candidate_k, self.fused_k, self.final_k) < 1:
            raise ValueError("candidate_k / fused_k / final_k 必须为正整数")
        if self.final_k > self.fused_k:
            raise ValueError("final_k 不能大于 fused_k")
        if self.candidate_k < self.final_k:
            raise ValueError("candidate_k 不能小于 final_k")
        if self.rerank_top_n < self.final_k:
            raise ValueError("rerank_top_n 不能小于 final_k")
        if not 0.0 <= self.rerank_threshold <= 1.0:
            raise ValueError("rerank_threshold 必须在 [0, 1] 之间")
        if not 0.0 <= self.rerank_delta <= 1.0:
            raise ValueError("rerank_delta 必须在 [0, 1] 之间")
        if (
            self.rerank_threshold > 0 or self.rerank_delta > 0
        ) and not self.rerank_enabled:
            raise ValueError(
                "设置 rerank_threshold / rerank_delta 前必须启用 rerank_enabled"
            )
        if self.context_token_budget < 500:
            raise ValueError("context_token_budget 不能小于 500")

    @classmethod
    def from_settings(cls) -> "RetrievalConfig":
        settings = get_settings()
        return cls(
            candidate_k=settings.candidate_k,
            fused_k=settings.fused_k,
            final_k=settings.final_k,
            hybrid_enabled=settings.hybrid_enabled,
            rerank_enabled=settings.rerank_enabled,
            rerank_top_n=settings.rerank_top_n,
            rerank_threshold=settings.rerank_threshold,
            rerank_delta=settings.rerank_delta,
            rewrite_enabled=settings.rewrite_enabled,
            context_token_budget=settings.context_token_budget,
        )

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class Retrieved:
    chunk_id: int
    document: Document
    content: str
    heading_path: list[str]
    chunk_index: int
    content_hash: str | None
    token_count: int
    score: float = 0.0
    origin: Origin = Origin.DENSE

    @property
    def key(self) -> int:
        return self.chunk_id


@dataclass
class RetrievalResult:
    items: list[Retrieved]
    rerank_ok: bool = True
    degraded: bool = False
    candidate_count: int = 0


def _to_item(
    chunk: DocumentChunk,
    document: Document,
    score: float,
    origin: Origin,
) -> Retrieved:
    return Retrieved(
        chunk_id=chunk.id,
        document=document,
        content=chunk.content,
        heading_path=list(chunk.heading_path or []),
        chunk_index=chunk.chunk_index,
        content_hash=chunk.content_hash,
        token_count=chunk.token_count or 0,
        score=score,
        origin=origin,
    )


async def _dense_recall(
    db: AsyncSession,
    vector: list[float],
    limit: int,
    source: str,
) -> list[Retrieved]:
    distance = DocumentChunk.embedding.cosine_distance(vector)
    stmt = (
        select(DocumentChunk, Document, (1 - distance).label("score"))
        .join(Document, Document.id == DocumentChunk.document_id)
        .where(
            Document.is_deleted.is_(False),
            Document.source == source,
            DocumentChunk.embedding.is_not(None),
        )
        .order_by(distance)
        .limit(limit)
    )
    rows = (await db.execute(stmt)).all()
    return [
        _to_item(chunk, document, float(score), Origin.DENSE)
        for chunk, document, score in rows
    ]


async def _sparse_recall(
    db: AsyncSession,
    query: str,
    limit: int,
    source: str,
) -> list[Retrieved]:
    segmented = segment_for_index(query)
    if not segmented:
        return []
    tsquery = func.plainto_tsquery("simple", segmented)
    rank = func.ts_rank_cd(DocumentChunk.content_tsv, tsquery)
    stmt = (
        select(DocumentChunk, Document, rank.label("rank"))
        .join(Document, Document.id == DocumentChunk.document_id)
        .where(
            Document.is_deleted.is_(False),
            Document.source == source,
            DocumentChunk.content_tsv.op("@@")(tsquery),
        )
        .order_by(rank.desc())
        .limit(limit)
    )
    rows = (await db.execute(stmt)).all()
    return [
        _to_item(chunk, document, float(score), Origin.SPARSE)
        for chunk, document, score in rows
    ]


def fuse_rrf(groups: list[list[Retrieved]], k: int = RRF_K) -> list[Retrieved]:
    merged: dict[int, Retrieved] = {}
    for group in groups:
        for rank, item in enumerate(group, start=1):
            current = merged.get(item.key)
            if current is None:
                current = Retrieved(
                    chunk_id=item.chunk_id,
                    document=item.document,
                    content=item.content,
                    heading_path=item.heading_path,
                    chunk_index=item.chunk_index,
                    content_hash=item.content_hash,
                    token_count=item.token_count,
                    score=0.0,
                    origin=Origin.FUSED,
                )
                merged[item.key] = current
            current.score += 1.0 / (k + rank)
    return sorted(merged.values(), key=lambda item: item.score, reverse=True)


def dedupe(items: list[Retrieved]) -> list[Retrieved]:
    seen: set[str] = set()
    result: list[Retrieved] = []
    for item in items:
        digest = item.content_hash or str(item.chunk_id)
        if digest in seen:
            continue
        seen.add(digest)
        result.append(item)
    return result


def merge_adjacent(
    items: list[Retrieved],
    max_chars: int = MERGE_MAX_CHARS,
) -> list[Retrieved]:
    merged: list[Retrieved] = []
    for item in items:
        if not merged:
            merged.append(item)
            continue
        previous = merged[-1]
        same_doc = previous.document.id == item.document.id
        adjacent = item.chunk_index == previous.chunk_index + 1
        room = len(previous.content) + len(item.content) <= max_chars
        if same_doc and adjacent and room:
            previous.content = f"{previous.content}\n{item.content}"
            previous.chunk_index = item.chunk_index
        else:
            merged.append(item)
    return merged


def within_budget(items: list[Retrieved], budget: int) -> list[Retrieved]:
    total = 0
    result: list[Retrieved] = []
    for item in items:
        size = item.token_count or int(len(item.content) * 0.7)
        if total + size > budget and result:
            continue
        total += size
        result.append(item)
    return result


async def search(
    db: AsyncSession,
    query: str,
    config: RetrievalConfig | None = None,
    source: str = "internal",
) -> RetrievalResult:
    config = config or RetrievalConfig.from_settings()

    vector = await embed_query(query)
    candidates = await _dense_recall(db, vector, config.candidate_k, source)

    if config.hybrid_enabled:
        try:
            sparse = await _sparse_recall(
                db, query, config.candidate_k, source
            )
            candidates = fuse_rrf([candidates, sparse])[: config.fused_k]
        except Exception:
            logger.warning(
                "sparse recall failed, dense only", exc_info=True
            )
            candidates = candidates[: config.fused_k]
    else:
        candidates = candidates[: config.fused_k]

    candidates = dedupe(candidates)
    if not candidates:
        return RetrievalResult(items=[], candidate_count=0)

    rerank_ok = True
    degraded = False
    if config.rerank_enabled:
        candidates, rerank_ok = await _rerank(query, candidates, config)
        degraded = not rerank_ok

    if config.rerank_enabled and rerank_ok:
        candidates = filter_by_relevance(candidates, config)

    return RetrievalResult(
        items=candidates[: config.final_k],
        rerank_ok=rerank_ok,
        degraded=degraded,
        candidate_count=len(candidates),
    )


def filter_by_relevance(
    items: list[Retrieved], config: RetrievalConfig
) -> list[Retrieved]:
    """Keep items above the absolute threshold and within top1 - delta."""
    if not items:
        return []
    floor = items[0].score - config.rerank_delta
    return [
        item
        for item in items
        if item.score >= config.rerank_threshold and item.score >= floor
    ]


async def _rerank(
    query: str,
    candidates: list[Retrieved],
    config: RetrievalConfig,
) -> tuple[list[Retrieved], bool]:
    pool = candidates[: config.rerank_top_n]
    try:
        scores = await rerank_pairs(
            query,
            [
                f"《{item.document.title}》\n{item.content}"
                for item in pool
            ],
        )
    except Exception:
        logger.warning("rerank failed, falling back to fused order", exc_info=True)
        return candidates, False
    if len(scores) != len(pool):
        logger.warning(
            "rerank returned %d scores for %d passages", len(scores), len(pool)
        )
        return candidates, False
    for item, score in zip(pool, scores):
        item.score = float(score)
        item.origin = Origin.RERANK
    return sorted(pool, key=lambda item: item.score, reverse=True), True


def to_citation(item: Retrieved, index: int | None = None) -> dict:
    return {
        "document_id": str(item.document.id),
        "document_title": item.document.title,
        "chunk_index": item.chunk_index,
        "heading_path": item.heading_path or [],
        "snippet": item.content[:300],
        "score": round(item.score, 6),
        "origin": item.origin.value
        if isinstance(item.origin, Origin)
        else str(item.origin),
        "index": index,
    }


def build_context(items: list[Retrieved]) -> str:
    lines: list[str] = []
    for index, item in enumerate(items, start=1):
        heading = " > ".join(item.heading_path or [])
        prefix = f"[{index}] 文档《{item.document.title}》"
        if heading:
            prefix += f" 章节：{heading}"
        lines.append(f"{prefix}\n{item.content}")
    return "\n\n".join(lines)
