import uuid
from datetime import datetime

from pydantic import BaseModel, Field

from app.schemas.user import UserBrief


class TicketAttachmentOut(BaseModel):
    id: uuid.UUID
    filename: str
    mime_type: str
    size_bytes: int
    uploaded_by: UserBrief
    created_at: datetime


class TicketEventOut(BaseModel):
    id: int
    actor: UserBrief
    action: str
    from_status: str | None
    to_status: str | None
    comment: str | None
    created_at: datetime


class TicketSummary(BaseModel):
    id: uuid.UUID
    ticket_no: str
    title: str
    type: str
    priority: str
    status: str
    is_backfilled: bool
    created_by: UserBrief
    assignee: UserBrief | None
    created_at: datetime
    updated_at: datetime


class TicketOut(TicketSummary):
    description: str
    expected_at: datetime | None
    resolution: str | None
    version: int
    attachments: list[TicketAttachmentOut]
    events: list[TicketEventOut]
    available_actions: list[str]


class TicketListResponse(BaseModel):
    items: list[TicketSummary]
    total: int
    page: int
    page_size: int


class TicketUpdate(BaseModel):
    version: int
    title: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = Field(default=None, min_length=1)
    type: str | None = None
    priority: str | None = None
    expected_at: datetime | None = None


class ApproveRequest(BaseModel):
    version: int
    assignee_id: uuid.UUID | None = None
    comment: str | None = Field(default=None, max_length=2000)


class RejectRequest(BaseModel):
    version: int
    comment: str = Field(min_length=1, max_length=2000)


class AssignRequest(BaseModel):
    version: int
    assignee_id: uuid.UUID


class CompleteRequest(BaseModel):
    version: int
    resolution: str | None = Field(default=None, max_length=4000)


class ModifyCompleteRequest(BaseModel):
    version: int
    comment: str | None = Field(default=None, max_length=2000)


class ConfirmRequest(BaseModel):
    version: int
    resolved: bool
    comment: str | None = Field(default=None, max_length=2000)


class AttachmentDownloadResponse(BaseModel):
    download_url: str
    expires_in: int
