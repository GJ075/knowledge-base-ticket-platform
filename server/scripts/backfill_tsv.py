"""Backfill full-text vectors for chunks created before 0008_retrieval_v2.

Usage (inside the api container):
    python -m scripts.backfill_tsv
"""

import asyncio

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import NullPool

from app.core.config import get_settings
from app.models.document import DocumentChunk
from app.services.text_index import segment_for_index

settings = get_settings()
BATCH = 100


async def main() -> None:
    engine = create_async_engine(settings.database_url, poolclass=NullPool)
    factory = async_sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False
    )
    total = 0
    async with factory() as db:
        while True:
            rows = (
                await db.execute(
                    select(DocumentChunk.id, DocumentChunk.content)
                    .where(DocumentChunk.content_tsv.is_(None))
                    .limit(BATCH)
                )
            ).all()
            if not rows:
                break
            for chunk_id, content in rows:
                await db.execute(
                    update(DocumentChunk)
                    .where(DocumentChunk.id == chunk_id)
                    .values(
                        content_tsv=func.to_tsvector(
                            "simple", segment_for_index(content)
                        )
                    )
                )
            await db.commit()
            total += len(rows)
            print(f"backfilled {total}")
    await engine.dispose()
    print(f"done, {total} chunks updated")


if __name__ == "__main__":
    asyncio.run(main())
