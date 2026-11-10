import uuid
from datetime import datetime

from pydantic import BaseModel, Field

from app.schemas.user import UserBrief


class DocumentOut(BaseModel):
    id: uuid.UUID
    title: str
    filename: str
    mime_type: str
    size_bytes: int
    index_status: str
    uploaded_by: UserBrief
    created_at: datetime
    updated_at: datetime


class DocumentChangeOut(BaseModel):
    id: uuid.UUID
    action: str
    status: str
    document_id: uuid.UUID | None
    document_title: str | None
    title: str | None
    filename: str | None
    mime_type: str | None
    size_bytes: int | None
    requested_by: UserBrief
    reviewed_by: UserBrief | None
    review_comment: str | None
    created_at: datetime
    reviewed_at: datetime | None


class DocumentListResponse(BaseModel):
    items: list[DocumentOut]
    total: int
    page: int
    page_size: int


class DocumentChangeListResponse(BaseModel):
    items: list[DocumentChangeOut]
    total: int
    page: int
    page_size: int


class DocumentActionResponse(BaseModel):
    mode: str
    document: DocumentOut | None = None
    change: DocumentChangeOut | None = None


class ReviewRequest(BaseModel):
    comment: str | None = Field(default=None, max_length=2000)


class RejectRequest(BaseModel):
    comment: str = Field(min_length=1, max_length=2000)


class DownloadResponse(BaseModel):
    download_url: str
    expires_in: int
