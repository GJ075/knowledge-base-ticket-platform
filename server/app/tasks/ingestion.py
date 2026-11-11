import asyncio
import uuid

from sqlalchemy import delete, func
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import NullPool

from app.core.config import get_settings
from app.models.document import Document, DocumentChunk
from app.services.chunking import structure_chunks
from app.services.document_metadata import extract_metadata
from app.services.document_parser import parse_document
from app.services.embedding_client import embed_texts_sync
from app.services.storage import get_bytes_async, remove_object_async
from app.services.text_index import segment_for_index
from app.tasks.celery_app import celery_app

settings = get_settings()


async def run_index_document(
    document_id: str,
    old_object_key: str | None = None,
) -> None:
    document_uuid = uuid.UUID(document_id)
    engine = create_async_engine(
        settings.database_url,
        poolclass=NullPool,
    )
    session_factory = async_sessionmaker(
        engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )
    try:
        async with session_factory() as db:
            document = await db.get(Document, document_uuid)
            if not document or document.is_deleted:
                return
            document.index_status = "indexing"
            await db.commit()

            data = await get_bytes_async(
                settings.minio_document_bucket, document.object_key
            )
            text = parse_document(document.filename, data)
            for field, value in extract_metadata(document.title, text).items():
                if not getattr(document, field, None):
                    setattr(document, field, value)

            chunks = structure_chunks(text)
            if not chunks:
                raise ValueError("文档没有可索引的分块")

            vectors = await asyncio.to_thread(
                embed_texts_sync, [chunk.content for chunk in chunks]
            )
            if len(vectors) != len(chunks):
                raise ValueError(
                    "embedding 返回数量与分块数量不一致"
                )

            await db.execute(
                delete(DocumentChunk).where(
                    DocumentChunk.document_id == document_uuid
                )
            )
            db.add_all(
                [
                    DocumentChunk(
                        document_id=document_uuid,
                        chunk_index=index,
                        content=chunk.content,
                        heading_path=chunk.heading_path,
                        unit_type=chunk.unit_type,
                        char_count=chunk.char_count,
                        token_count=chunk.token_count,
                        content_hash=chunk.content_hash,
                        content_tsv=func.to_tsvector(
                            "simple", segment_for_index(chunk.content)
                        ),
                        embedding=vector,
                    )
                    for index, (chunk, vector) in enumerate(
                        zip(chunks, vectors)
                    )
                ]
            )
            document.index_status = "ready"
            await db.commit()

        if old_object_key:
            await remove_object_async(
                settings.minio_document_bucket, old_object_key
            )
    except Exception:
        async with session_factory() as db:
            document = await db.get(Document, document_uuid)
            if document:
                document.index_status = "failed"
                await db.commit()
        raise
    finally:
        await engine.dispose()


@celery_app.task(
    bind=True,
    max_retries=3,
    name="index_document",
)
def index_document_task(
    self,
    document_id: str,
    old_object_key: str | None = None,
) -> None:
    try:
        asyncio.run(run_index_document(document_id, old_object_key))
    except Exception as exc:
        if self.request.retries >= self.max_retries:
            raise
        raise self.retry(
            exc=exc,
            countdown=10 * (2 ** self.request.retries),
        )
