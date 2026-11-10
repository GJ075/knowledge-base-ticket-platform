from datetime import datetime
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

from app.core.deps import get_current_user
from app.db.session import get_db
from app.models.user import User
from app.schemas.ticket import (
    ApproveRequest,
    AssignRequest,
    AttachmentDownloadResponse,
    CompleteRequest,
    ConfirmRequest,
    ModifyCompleteRequest,
    RejectRequest,
    TicketAttachmentOut,
    TicketListResponse,
    TicketOut,
    TicketUpdate,
)
from app.services import ticket_service

router = APIRouter(prefix="/tickets", tags=["tickets"])


@router.post("", response_model=TicketOut, status_code=201)
async def create_ticket(
    title: str = Form(..., min_length=1, max_length=255),
    description: str = Form(...),
    type: str = Form(...),
    priority: str = Form(...),
    expected_at: datetime | None = Form(default=None),
    is_backfilled: bool = Form(default=False),
    backfill_created_at: datetime | None = Form(default=None),
    submitter_id: UUID | None = Form(default=None),
    files: list[UploadFile] = File(default=[]),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> TicketOut:
    payload_files = []
    for file in files:
        data = await file.read()
        payload_files.append(
            (file.filename or "attachment", file.content_type, data)
        )
    return await ticket_service.create_ticket(
        db,
        user,
        title,
        description,
        type,
        priority,
        expected_at,
        payload_files,
        is_backfilled=is_backfilled,
        backfill_created_at=backfill_created_at,
        submitter_id=submitter_id,
    )


@router.get("", response_model=TicketListResponse)
async def list_tickets(
    status: str | None = Query(default=None),
    type: str | None = Query(default=None),
    priority: str | None = Query(default=None),
    assignee_id: UUID | None = Query(default=None),
    keyword: str = Query(default=""),
    date_from: datetime | None = Query(default=None),
    date_to: datetime | None = Query(default=None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> TicketListResponse:
    return await ticket_service.list_tickets(
        db,
        user,
        status,
        type,
        priority,
        assignee_id,
        keyword,
        date_from,
        date_to,
        page,
        page_size,
    )


@router.get("/{ticket_id}", response_model=TicketOut)
async def get_ticket(
    ticket_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> TicketOut:
    return await ticket_service.ticket_detail(db, user, ticket_id)


@router.patch("/{ticket_id}", response_model=TicketOut)
async def update_ticket(
    ticket_id: UUID,
    payload: TicketUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> TicketOut:
    return await ticket_service.edit_ticket(
        db, user, ticket_id, payload
    )


@router.post("/{ticket_id}/approve", response_model=TicketOut)
async def approve_ticket(
    ticket_id: UUID,
    payload: ApproveRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> TicketOut:
    return await ticket_service.approve_ticket(
        db, user, ticket_id, payload
    )


@router.post("/{ticket_id}/reject", response_model=TicketOut)
async def reject_ticket(
    ticket_id: UUID,
    payload: RejectRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> TicketOut:
    return await ticket_service.reject_ticket(
        db, user, ticket_id, payload
    )


@router.post("/{ticket_id}/assign", response_model=TicketOut)
async def assign_ticket(
    ticket_id: UUID,
    payload: AssignRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> TicketOut:
    return await ticket_service.assign_ticket(
        db, user, ticket_id, payload
    )


@router.post("/{ticket_id}/complete", response_model=TicketOut)
async def complete_ticket(
    ticket_id: UUID,
    payload: CompleteRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> TicketOut:
    return await ticket_service.complete_ticket(
        db, user, ticket_id, payload
    )


@router.post(
    "/{ticket_id}/modify-complete", response_model=TicketOut
)
async def modify_complete_ticket(
    ticket_id: UUID,
    payload: ModifyCompleteRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> TicketOut:
    return await ticket_service.modify_complete_ticket(
        db, user, ticket_id, payload
    )


@router.post("/{ticket_id}/confirm", response_model=TicketOut)
async def confirm_ticket(
    ticket_id: UUID,
    payload: ConfirmRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> TicketOut:
    return await ticket_service.confirm_ticket(
        db, user, ticket_id, payload
    )


@router.post(
    "/{ticket_id}/attachments",
    response_model=TicketAttachmentOut,
    status_code=201,
)
async def add_attachment(
    ticket_id: UUID,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> TicketAttachmentOut:
    data = await file.read()
    return await ticket_service.add_attachment(
        db,
        user,
        ticket_id,
        file.filename or "attachment",
        file.content_type,
        data,
    )


@router.delete(
    "/{ticket_id}/attachments/{attachment_id}",
    status_code=204,
)
async def delete_attachment(
    ticket_id: UUID,
    attachment_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> None:
    await ticket_service.delete_attachment(
        db, user, ticket_id, attachment_id
    )


@router.get(
    "/{ticket_id}/attachments/{attachment_id}/download",
    response_model=AttachmentDownloadResponse,
)
async def download_attachment(
    ticket_id: UUID,
    attachment_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> AttachmentDownloadResponse:
    return await ticket_service.attachment_download(
        db, user, ticket_id, attachment_id
    )


@router.get(
    "/{ticket_id}/attachments/{attachment_id}/download/file"
)
async def download_attachment_file(
    ticket_id: UUID,
    attachment_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Response:
    attachment, data = await ticket_service.attachment_file(
        db, user, ticket_id, attachment_id
    )
    encoded_filename = quote(attachment.filename)
    return Response(
        content=data,
        media_type=attachment.mime_type,
        headers={
            "Content-Disposition": (
                "attachment; filename*=UTF-8''" + encoded_filename
            )
        },
    )
