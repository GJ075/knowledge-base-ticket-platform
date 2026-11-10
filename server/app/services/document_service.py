import logging
import uuid
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import delete, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.config import get_settings
from app.core.errors import AppError
from app.models.document import Document, DocumentChange, DocumentChunk
from app.models.user import User
from app.schemas.document import (
    BatchDeleteResponse,
    BatchIdsResponse,
    BatchItem,
    DocumentActionResponse,
    DocumentChangeListResponse,
    DocumentChangeOut,
    DocumentListResponse,
    DocumentOut,
    SkippedItem,
    TrashDocumentOut,
    TrashListResponse,
)
from app.schemas.user import UserBrief
from app.services.document_parser import validate_upload
from app.services.mime_types import guess_mime_type
from app.services.storage import put_bytes_async, remove_object_async
from app.tasks.celery_app import celery_app

settings = get_settings()
BUCKET = settings.minio_document_bucket
logger = logging.getLogger("app")


async def _safe_rollback(db: AsyncSession) -> None:
    try:
        await db.rollback()
    except Exception as exc:
        logger.warning(
            "database rollback failed: %s: %s",
            type(exc).__name__,
            exc,
        )


def _new_object_key(filename: str) -> str:
    return f"documents/{uuid.uuid4().hex}{Path(filename).suffix.lower()}"


async def _store_file(filename: str, data: bytes) -> tuple[str, str, int]:
    validate_upload(filename, data)
    object_key = _new_object_key(filename)
    mime_type = guess_mime_type(filename)
    await put_bytes_async(BUCKET, object_key, data, mime_type)
    return object_key, mime_type, len(data)


def _user_brief(user: User) -> UserBrief:
    return UserBrief.model_validate(user)


def document_to_out(document: Document) -> DocumentOut:
    return DocumentOut(
        id=document.id,
        title=document.title,
        filename=document.filename,
        mime_type=document.mime_type,
        size_bytes=document.size_bytes,
        index_status=document.index_status,
        uploaded_by=_user_brief(document.uploader),
        created_at=document.created_at,
        updated_at=document.updated_at,
    )


def change_to_out(change: DocumentChange) -> DocumentChangeOut:
    document_title = change.title or (
        change.document.title if change.document else None
    )
    return DocumentChangeOut(
        id=change.id,
        action=change.action,
        status=change.status,
        document_id=change.document_id,
        document_title=document_title,
        title=change.title,
        filename=change.filename,
        mime_type=change.mime_type,
        size_bytes=change.size_bytes,
        requested_by=_user_brief(change.requester),
        reviewed_by=(
            _user_brief(change.reviewer) if change.reviewer else None
        ),
        review_comment=change.review_comment,
        created_at=change.created_at,
        reviewed_at=change.reviewed_at,
    )


def _page(page: int, page_size: int) -> tuple[int, int, int]:
    page = max(page, 1)
    page_size = min(max(page_size, 1), 100)
    return page, page_size, (page - 1) * page_size


async def _pending_change_id(
    db: AsyncSession, document_id: uuid.UUID
) -> uuid.UUID | None:
    return (
        await db.execute(
            select(DocumentChange.id).where(
                DocumentChange.document_id == document_id,
                DocumentChange.status == "pending",
            )
        )
    ).scalar_one_or_none()


def _move_to_trash(document: Document) -> None:
    document.is_deleted = True
    document.deleted_at = datetime.now(timezone.utc)


async def _load_document(
    db: AsyncSession, document_id: uuid.UUID
) -> Document:
    document = (
        await db.execute(
            select(Document)
            .options(selectinload(Document.uploader))
            .where(
                Document.id == document_id,
                Document.is_deleted.is_(False),
            )
        )
    ).scalar_one_or_none()
    if not document:
        raise AppError("NOT_FOUND", "文档不存在", 404)
    return document


async def get_document_model(
    db: AsyncSession, document_id: uuid.UUID
) -> Document:
    return await _load_document(db, document_id)


async def list_documents(
    db: AsyncSession,
    keyword: str,
    page: int,
    page_size: int,
) -> DocumentListResponse:
    page, page_size, offset = _page(page, page_size)
    filters = [Document.is_deleted.is_(False)]
    if keyword:
        pattern = f"%{keyword}%"
        filters.append(
            or_(
                Document.title.ilike(pattern),
                Document.filename.ilike(pattern),
            )
        )

    count_query = select(func.count()).select_from(Document).where(*filters)
    query = (
        select(Document)
        .options(selectinload(Document.uploader))
        .where(*filters)
        .order_by(Document.created_at.desc())
        .offset(offset)
        .limit(page_size)
    )
    total = (await db.execute(count_query)).scalar_one()
    documents = (await db.execute(query)).scalars().all()
    return DocumentListResponse(
        items=[document_to_out(document) for document in documents],
        total=total,
        page=page,
        page_size=page_size,
    )


async def document_detail(
    db: AsyncSession, document_id: uuid.UUID
) -> DocumentOut:
    return document_to_out(await _load_document(db, document_id))


async def create_document(
    db: AsyncSession,
    user: User,
    title: str,
    filename: str,
    data: bytes,
) -> DocumentActionResponse:
    title = title.strip()
    if not title:
        raise AppError("VALIDATION_ERROR", "标题不能为空", 422)
    if len(title) > 255:
        raise AppError(
            "VALIDATION_ERROR", "标题不能超过 255 个字符", 422
        )
    filename = Path(filename or "file").name or "file"
    object_key, mime_type, size_bytes = await _store_file(
        filename, data
    )
    committed = False
    try:
        if user.role == "leader":
            document = Document(
                title=title,
                filename=filename,
                object_key=object_key,
                mime_type=mime_type,
                size_bytes=size_bytes,
                index_status="pending",
                uploaded_by=user.id,
            )
            document.uploader = user
            db.add(document)
            await db.commit()
            committed = True
            celery_app.send_task(
                "index_document", args=[str(document.id)]
            )
            document = await _load_document(db, document.id)
            return DocumentActionResponse(
                mode="direct", document=document_to_out(document)
            )

        change = DocumentChange(
            action="create",
            status="pending",
            title=title,
            filename=filename,
            object_key=object_key,
            mime_type=mime_type,
            size_bytes=size_bytes,
            requested_by=user.id,
        )
        change.requester = user
        db.add(change)
        await db.commit()
        committed = True
        return DocumentActionResponse(
            mode="pending_approval", change=change_to_out(change)
        )
    except Exception:
        await _safe_rollback(db)
        if not committed:
            try:
                await remove_object_async(BUCKET, object_key)
            except Exception:
                logger.warning(
                    "failed to remove orphan document %s",
                    object_key,
                    exc_info=True,
                )
        raise


async def update_document(
    db: AsyncSession,
    user: User,
    document_id: uuid.UUID,
    title: str | None,
    filename: str | None,
    data: bytes | None,
) -> DocumentActionResponse:
    if title is None and data is None:
        raise AppError(
            "VALIDATION_ERROR", "标题和文件至少提供一个", 422
        )
    document = await _load_document(db, document_id)
    if title is not None:
        title = title.strip()
        if not title:
            raise AppError("VALIDATION_ERROR", "标题不能为空", 422)
        if len(title) > 255:
            raise AppError(
                "VALIDATION_ERROR",
                "标题不能超过 255 个字符",
                422,
            )

    if user.role == "leader":
        old_object_key = None
        should_index = False
        new_key = None
        committed = False
        try:
            if title is not None:
                document.title = title
            if data is not None:
                safe_filename = (
                    Path(filename or document.filename).name
                    or document.filename
                )
                new_key, mime_type, size_bytes = await _store_file(
                    safe_filename, data
                )
                old_object_key = document.object_key
                document.filename = safe_filename
                document.object_key = new_key
                document.mime_type = mime_type
                document.size_bytes = size_bytes
                document.index_status = "pending"
                await db.execute(
                    delete(DocumentChunk).where(
                        DocumentChunk.document_id == document.id
                    )
                )
                should_index = True
            await db.commit()
            committed = True
        except Exception:
            await _safe_rollback(db)
            if new_key and not committed:
                try:
                    await remove_object_async(BUCKET, new_key)
                except Exception:
                    logger.warning(
                        "failed to remove orphan document %s",
                        new_key,
                        exc_info=True,
                    )
            raise
        if should_index:
            celery_app.send_task(
                "index_document",
                args=[str(document.id), old_object_key],
            )
        document = await _load_document(db, document.id)
        return DocumentActionResponse(
            mode="direct", document=document_to_out(document)
        )

    if await _pending_change_id(db, document.id):
        raise AppError(
            "DOC_CHANGE_ALREADY_PENDING", "该文档已有待审批变更", 409
        )

    new_key = None
    committed = False
    try:
        change = DocumentChange(
            action="update",
            status="pending",
            document_id=document.id,
            title=title,
            requested_by=user.id,
        )
        if data is not None:
            safe_filename = (
                Path(filename or document.filename).name
                or document.filename
            )
            new_key, mime_type, size_bytes = await _store_file(
                safe_filename, data
            )
            change.filename = safe_filename
            change.object_key = new_key
            change.mime_type = mime_type
            change.size_bytes = size_bytes
        change.requester = user
        change.document = document
        db.add(change)
        await db.commit()
        committed = True
    except Exception:
        await _safe_rollback(db)
        if new_key and not committed:
            try:
                await remove_object_async(BUCKET, new_key)
            except Exception:
                logger.warning(
                    "failed to remove orphan document %s",
                    new_key,
                    exc_info=True,
                )
        raise
    return DocumentActionResponse(
        mode="pending_approval", change=change_to_out(change)
    )


async def delete_document(
    db: AsyncSession,
    user: User,
    document_id: uuid.UUID,
) -> DocumentActionResponse:
    document = await _load_document(db, document_id)

    if user.role == "leader":
        if await _pending_change_id(db, document.id):
            raise AppError(
                "DOC_CHANGE_ALREADY_PENDING",
                "该文档已有待审批变更",
                409,
            )
        _move_to_trash(document)
        await db.commit()
        return DocumentActionResponse(mode="direct")

    if await _pending_change_id(db, document.id):
        raise AppError(
            "DOC_CHANGE_ALREADY_PENDING", "该文档已有待审批变更", 409
        )
    change = DocumentChange(
        action="delete",
        status="pending",
        document_id=document.id,
        title=document.title,
        requested_by=user.id,
    )
    change.requester = user
    change.document = document
    db.add(change)
    await db.commit()
    return DocumentActionResponse(
        mode="pending_approval", change=change_to_out(change)
    )


async def reindex_document(
    db: AsyncSession,
    user: User,
    document_id: uuid.UUID,
) -> DocumentActionResponse:
    if user.role != "leader":
        raise AppError("AUTH_FORBIDDEN", "需要领导权限", 403)
    document = await _load_document(db, document_id)
    document.index_status = "pending"
    await db.commit()
    celery_app.send_task("index_document", args=[str(document.id)])
    document = await _load_document(db, document.id)
    return DocumentActionResponse(
        mode="direct", document=document_to_out(document)
    )


async def _load_change(
    db: AsyncSession,
    change_id: uuid.UUID,
    lock: bool,
) -> DocumentChange:
    query = (
        select(DocumentChange)
        .options(
            selectinload(DocumentChange.requester),
            selectinload(DocumentChange.reviewer),
            selectinload(DocumentChange.document),
        )
        .where(DocumentChange.id == change_id)
    )
    if lock:
        query = query.with_for_update()
    change = (await db.execute(query)).scalar_one_or_none()
    if not change:
        raise AppError("NOT_FOUND", "变更不存在", 404)
    return change


async def list_changes(
    db: AsyncSession,
    user: User,
    status: str | None,
    page: int,
    page_size: int,
) -> DocumentChangeListResponse:
    page, page_size, offset = _page(page, page_size)
    filters = []
    if status:
        filters.append(DocumentChange.status == status)
    if user.role != "leader":
        filters.append(DocumentChange.requested_by == user.id)

    count_query = select(func.count()).select_from(DocumentChange)
    query = select(DocumentChange).options(
        selectinload(DocumentChange.requester),
        selectinload(DocumentChange.reviewer),
        selectinload(DocumentChange.document),
    )
    if filters:
        count_query = count_query.where(*filters)
        query = query.where(*filters)

    total = (await db.execute(count_query)).scalar_one()
    changes = (
        await db.execute(
            query.order_by(DocumentChange.created_at.desc())
            .offset(offset)
            .limit(page_size)
        )
    ).scalars().all()
    return DocumentChangeListResponse(
        items=[change_to_out(change) for change in changes],
        total=total,
        page=page,
        page_size=page_size,
    )


async def change_detail(
    db: AsyncSession,
    user: User,
    change_id: uuid.UUID,
) -> DocumentChangeOut:
    change = await _load_change(db, change_id, lock=False)
    if user.role != "leader" and change.requested_by != user.id:
        raise AppError("AUTH_FORBIDDEN", "无权查看该变更", 403)
    return change_to_out(change)


async def approve_change(
    db: AsyncSession,
    reviewer: User,
    change_id: uuid.UUID,
    comment: str | None,
) -> DocumentActionResponse:
    if reviewer.role != "leader":
        raise AppError("AUTH_FORBIDDEN", "需要领导权限", 403)
    change = await _load_change(db, change_id, lock=True)
    if change.status != "pending":
        raise AppError(
            "DOC_CHANGE_NOT_PENDING", "变更不是待审批状态", 409
        )

    document: Document | None = None
    index_document_id: uuid.UUID | None = None
    response_document_id: uuid.UUID | None = None
    old_object_key: str | None = None

    if change.action == "create":
        if not change.title or not change.object_key:
            raise AppError("VALIDATION_ERROR", "变更信息不完整", 422)
        document = Document(
            title=change.title,
            filename=change.filename or "未命名文件",
            object_key=change.object_key,
            mime_type=change.mime_type or "application/octet-stream",
            size_bytes=change.size_bytes or 0,
            index_status="pending",
            uploaded_by=change.requested_by,
        )
        document.uploader = change.requester
        db.add(document)
        await db.flush()
        index_document_id = document.id
        response_document_id = document.id
    elif change.action == "update":
        if not change.document_id:
            raise AppError("VALIDATION_ERROR", "变更缺少目标文档", 422)
        document = await _load_document(db, change.document_id)
        if change.title:
            document.title = change.title
        if change.object_key:
            old_object_key = document.object_key
            document.filename = change.filename or document.filename
            document.object_key = change.object_key
            document.mime_type = change.mime_type or document.mime_type
            document.size_bytes = change.size_bytes or document.size_bytes
            document.index_status = "pending"
            await db.execute(
                delete(DocumentChunk).where(
                    DocumentChunk.document_id == document.id
                )
            )
            index_document_id = document.id
        response_document_id = document.id
    elif change.action == "delete":
        if not change.document_id:
            raise AppError("VALIDATION_ERROR", "变更缺少目标文档", 422)
        document = await _load_document(db, change.document_id)
        _move_to_trash(document)
    else:
        raise AppError("VALIDATION_ERROR", "未知的变更类型", 422)

    change.status = "approved"
    change.reviewed_by = reviewer.id
    change.reviewer = reviewer
    change.reviewed_at = datetime.now(timezone.utc)
    change.review_comment = comment
    await db.commit()

    if index_document_id:
        celery_app.send_task(
            "index_document",
            args=[str(index_document_id), old_object_key],
        )

    response_document = (
        await _load_document(db, response_document_id)
        if response_document_id
        else None
    )

    return DocumentActionResponse(
        mode="direct",
        document=(
            document_to_out(response_document)
            if response_document
            else None
        ),
        change=change_to_out(change),
    )


async def reject_change(
    db: AsyncSession,
    reviewer: User,
    change_id: uuid.UUID,
    comment: str,
) -> DocumentActionResponse:
    if reviewer.role != "leader":
        raise AppError("AUTH_FORBIDDEN", "需要领导权限", 403)
    change = await _load_change(db, change_id, lock=True)
    if change.status != "pending":
        raise AppError(
            "DOC_CHANGE_NOT_PENDING", "变更不是待审批状态", 409
        )
    if change.object_key:
        await remove_object_async(BUCKET, change.object_key)
    change.status = "rejected"
    change.reviewed_by = reviewer.id
    change.reviewer = reviewer
    change.reviewed_at = datetime.now(timezone.utc)
    change.review_comment = comment
    await db.commit()
    return DocumentActionResponse(
        mode="direct", change=change_to_out(change)
    )


async def batch_delete(
    db: AsyncSession,
    user: User,
    ids: list[uuid.UUID],
) -> BatchDeleteResponse:
    ids = list(dict.fromkeys(ids))
    documents = (
        await db.execute(select(Document).where(Document.id.in_(ids)))
    ).scalars().all()
    by_id = {document.id: document for document in documents}
    deleted: list[BatchItem] = []
    submitted: list[BatchItem] = []
    skipped: list[SkippedItem] = []

    for document_id in ids:
        document = by_id.get(document_id)
        if not document:
            skipped.append(
                SkippedItem(id=document_id, reason="文档不存在")
            )
            continue
        if document.is_deleted:
            skipped.append(
                SkippedItem(
                    id=document_id,
                    title=document.title,
                    reason="文档已在回收站",
                )
            )
            continue
        if await _pending_change_id(db, document_id):
            skipped.append(
                SkippedItem(
                    id=document_id,
                    title=document.title,
                    reason="该文档已有待审批变更",
                )
            )
            continue
        if user.role == "leader":
            _move_to_trash(document)
            deleted.append(
                BatchItem(id=document.id, title=document.title)
            )
        else:
            db.add(
                DocumentChange(
                    action="delete",
                    status="pending",
                    document_id=document.id,
                    title=document.title,
                    requested_by=user.id,
                )
            )
            submitted.append(
                BatchItem(id=document.id, title=document.title)
            )

    await db.commit()
    return BatchDeleteResponse(
        mode="direct" if user.role == "leader" else "pending_approval",
        deleted=deleted,
        submitted=submitted,
        skipped=skipped,
    )


async def list_trash(
    db: AsyncSession,
    keyword: str,
    page: int,
    page_size: int,
) -> TrashListResponse:
    page, page_size, offset = _page(page, page_size)
    filters = [
        Document.is_deleted.is_(True),
        Document.purged_at.is_(None),
    ]
    if keyword:
        pattern = f"%{keyword}%"
        filters.append(
            or_(
                Document.title.ilike(pattern),
                Document.filename.ilike(pattern),
            )
        )
    count_query = select(func.count()).select_from(Document).where(*filters)
    query = (
        select(Document)
        .options(selectinload(Document.uploader))
        .where(*filters)
        .order_by(Document.deleted_at.desc())
        .offset(offset)
        .limit(page_size)
    )
    total = (await db.execute(count_query)).scalar_one()
    documents = (await db.execute(query)).scalars().all()
    return TrashListResponse(
        items=[
            TrashDocumentOut(
                **document_to_out(document).model_dump(),
                deleted_at=document.deleted_at,
            )
            for document in documents
        ],
        total=total,
        page=page,
        page_size=page_size,
    )


async def restore_documents(
    db: AsyncSession, ids: list[uuid.UUID]
) -> BatchIdsResponse:
    ids = list(dict.fromkeys(ids))
    documents = (
        await db.execute(select(Document).where(Document.id.in_(ids)))
    ).scalars().all()
    by_id = {document.id: document for document in documents}
    processed: list[BatchItem] = []
    skipped: list[SkippedItem] = []

    for document_id in ids:
        document = by_id.get(document_id)
        if not document:
            skipped.append(
                SkippedItem(id=document_id, reason="文档不存在")
            )
            continue
        if not document.is_deleted:
            skipped.append(
                SkippedItem(
                    id=document_id,
                    title=document.title,
                    reason="文档不在回收站",
                )
            )
            continue
        if document.purged_at:
            skipped.append(
                SkippedItem(
                    id=document_id,
                    title=document.title,
                    reason="文档已彻底删除",
                )
            )
            continue
        if await _pending_change_id(db, document_id):
            skipped.append(
                SkippedItem(
                    id=document_id,
                    title=document.title,
                    reason="该文档已有待审批变更",
                )
            )
            continue
        document.is_deleted = False
        document.deleted_at = None
        processed.append(
            BatchItem(id=document.id, title=document.title)
        )

    await db.commit()
    return BatchIdsResponse(processed=processed, skipped=skipped)


async def purge_documents(
    db: AsyncSession, ids: list[uuid.UUID]
) -> BatchIdsResponse:
    ids = list(dict.fromkeys(ids))
    documents = (
        await db.execute(select(Document).where(Document.id.in_(ids)))
    ).scalars().all()
    by_id = {document.id: document for document in documents}
    processed: list[BatchItem] = []
    skipped: list[SkippedItem] = []
    object_keys: list[str] = []

    for document_id in ids:
        document = by_id.get(document_id)
        if not document:
            skipped.append(
                SkippedItem(id=document_id, reason="文档不存在")
            )
            continue
        if not document.is_deleted or document.purged_at:
            skipped.append(
                SkippedItem(
                    id=document_id,
                    title=document.title,
                    reason="文档不在回收站",
                )
            )
            continue
        if await _pending_change_id(db, document_id):
            skipped.append(
                SkippedItem(
                    id=document_id,
                    title=document.title,
                    reason="该文档已有待审批变更",
                )
            )
            continue
        await db.execute(
            delete(DocumentChunk).where(
                DocumentChunk.document_id == document.id
            )
        )
        document.purged_at = datetime.now(timezone.utc)
        object_keys.append(document.object_key)
        processed.append(
            BatchItem(id=document.id, title=document.title)
        )

    await db.commit()

    for object_key in object_keys:
        try:
            await remove_object_async(BUCKET, object_key)
        except Exception:
            logger.warning(
                "failed to remove document object %s",
                object_key,
                exc_info=True,
            )
    return BatchIdsResponse(processed=processed, skipped=skipped)


async def batch_review(
    db: AsyncSession,
    reviewer: User,
    ids: list[uuid.UUID],
    comment: str | None,
    approve: bool,
) -> BatchIdsResponse:
    processed: list[BatchItem] = []
    skipped: list[SkippedItem] = []
    for change_id in list(dict.fromkeys(ids)):
        change = await db.get(DocumentChange, change_id)
        title = (
            change.document.title
            if change and change.document
            else (change.title if change else None)
        )
        try:
            if approve:
                await approve_change(db, reviewer, change_id, comment)
            else:
                await reject_change(
                    db, reviewer, change_id, comment or ""
                )
            processed.append(BatchItem(id=change_id, title=title or "变更"))
        except AppError as exc:
            skipped.append(
                SkippedItem(id=change_id, title=title, reason=exc.message)
            )
    return BatchIdsResponse(processed=processed, skipped=skipped)
