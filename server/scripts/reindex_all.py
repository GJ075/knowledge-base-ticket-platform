"""Re-parse and re-index every active document.

Usage (inside the api container):
    python -m scripts.reindex_all
"""

import asyncio

from sqlalchemy import select
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import NullPool

from app.core.config import get_settings
from app.models.document import Document
from app.tasks.ingestion import run_index_document

settings = get_settings()


async def main() -> None:
    engine = create_async_engine(settings.database_url, poolclass=NullPool)
    factory = async_sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False
    )
    async with factory() as db:
        document_ids = (
            await db.execute(
                select(Document.id)
                .where(Document.is_deleted.is_(False))
                .order_by(Document.created_at)
            )
        ).scalars().all()
    await engine.dispose()

    print(f"reindexing {len(document_ids)} documents")
    for index, document_id in enumerate(document_ids, start=1):
        await run_index_document(str(document_id))
        print(f"[{index}/{len(document_ids)}] {document_id} done")


if __name__ == "__main__":
    asyncio.run(main())
