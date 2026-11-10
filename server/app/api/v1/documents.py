from urllib.parse import quote
from uuid import UUID

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    Query,
    Response,
    UploadFile,
)
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.deps import get_current_user
from app.db.session import get_db
from app.models.user import User
from app.schemas.document import (
    DocumentActionResponse,
    DocumentListResponse,
    DocumentOut,
    DownloadResponse,
)
from app.services import document_service
from app.services.storage import get_bytes_async

router = APIRouter(prefix="/documents", tags=["documents"])
settings = get_settings()


@router.get("", response_model=DocumentListResponse)
async def list_documents(
    keyword: str = "",
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
) -> DocumentListResponse:
    return await document_service.list_documents(
        db, keyword, page, page_size
    )


@router.post("", response_model=DocumentActionResponse)
async def create_document(
    response: Response,
    file: UploadFile = File(...),
    title: str = Form(..., min_length=1, max_length=255),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> DocumentActionResponse:
    data = await file.read()
    result = await document_service.create_document(
        db,
        user,
        title,
        file.filename or "file",
        data,
    )
    response.status_code = 201 if result.mode == "direct" else 202
    return result


@router.get("/{document_id}", response_model=DocumentOut)
async def get_document(
    document_id: UUID,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
) -> DocumentOut:
    return await document_service.document_detail(db, document_id)


@router.get("/{document_id}/download", response_model=DownloadResponse)
async def download_document(
    document_id: UUID,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
) -> DownloadResponse:
    document = await document_service.get_document_model(db, document_id)
    return DownloadResponse(
        download_url=(
            f"{settings.public_api_url}/api/v1/documents/"
            f"{document.id}/download/file"
        ),
        expires_in=600,
    )


@router.get("/{document_id}/download/file")
async def download_document_file(
    document_id: UUID,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
) -> Response:
    document = await document_service.get_document_model(db, document_id)
    data = await get_bytes_async(
        settings.minio_document_bucket, document.object_key
    )
    encoded_filename = quote(document.filename)
    return Response(
        content=data,
        media_type=document.mime_type,
        headers={
            "Content-Disposition": (
                "attachment; filename*=UTF-8''" + encoded_filename
            )
        },
    )


@router.put("/{document_id}", response_model=DocumentActionResponse)
async def update_document(
    document_id: UUID,
    file: UploadFile | None = File(default=None),
    title: str | None = Form(
        default=None, min_length=1, max_length=255
    ),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> DocumentActionResponse:
    data = await file.read() if file else None
    filename = file.filename if file else None
    return await document_service.update_document(
        db,
        user,
        document_id,
        title,
        filename,
        data,
    )


@router.delete("/{document_id}", response_model=DocumentActionResponse)
async def delete_document(
    document_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> DocumentActionResponse:
    return await document_service.delete_document(
        db, user, document_id
    )


@router.post(
    "/{document_id}/reindex", response_model=DocumentActionResponse
)
async def reindex_document(
    document_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> DocumentActionResponse:
    return await document_service.reindex_document(
        db, user, document_id
    )
