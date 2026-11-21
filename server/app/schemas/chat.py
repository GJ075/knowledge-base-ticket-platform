import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    conversation_id: uuid.UUID | None = None
    message: str = Field(min_length=1, max_length=4000)


class Citation(BaseModel):
    document_id: uuid.UUID
    document_title: str
    chunk_index: int
    snippet: str
    heading_path: list[str] | None = None
    score: float | None = None
    origin: str | None = None
    index: int | None = None


class MessageOut(BaseModel):
    id: uuid.UUID
    role: str
    content: str
    citations: list[Citation] | None
    citation_meta: dict | None = None
    created_at: datetime


class ConversationSummary(BaseModel):
    id: uuid.UUID
    title: str
    created_at: datetime
    updated_at: datetime


class ConversationListResponse(BaseModel):
    items: list[ConversationSummary]
    total: int
    page: int
    page_size: int


class ConversationDetail(BaseModel):
    id: uuid.UUID
    title: str
    created_at: datetime
    updated_at: datetime
    messages: list[MessageOut]


class RecitationItem(BaseModel):
    message_id: uuid.UUID
    citations: list[Citation]
    mode: str = "recomputed"
    degraded: bool = False


class RecitationResponse(BaseModel):
    items: list[RecitationItem]
