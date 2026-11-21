import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

ExpectedType = Literal["answerable", "unanswerable"]


class DocumentRef(BaseModel):
    id: uuid.UUID
    title: str


class TurnIn(BaseModel):
    question: str = Field(min_length=1, max_length=2000)
    reference_answer: str | None = Field(default=None, max_length=4000)
    expected_type: ExpectedType = "answerable"
    required_document_ids: list[uuid.UUID] = Field(default_factory=list)


class TurnOut(BaseModel):
    id: uuid.UUID
    turn_index: int
    question: str
    reference_answer: str | None
    expected_type: str
    required_document_ids: list[str]
    required_documents: list[DocumentRef] = Field(default_factory=list)


class CaseIn(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    tags: list[str] = Field(default_factory=list, max_length=20)
    turns: list[TurnIn] = Field(min_length=1, max_length=5)


class CaseUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=255)
    tags: list[str] | None = Field(default=None, max_length=20)


class CaseOut(BaseModel):
    id: uuid.UUID
    title: str
    tags: list[str]
    sort_order: int
    turns: list[TurnOut]


class DatasetCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    description: str | None = Field(default=None, max_length=2000)


class DatasetUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    description: str | None = Field(default=None, max_length=2000)


class RunSummary(BaseModel):
    id: uuid.UUID
    status: str
    retrieval_mode: str
    total_items: int
    completed_items: int
    created_at: datetime
    finished_at: datetime | None


class DatasetSummary(BaseModel):
    id: uuid.UUID
    name: str
    description: str | None
    is_archived: bool
    case_count: int
    turn_count: int
    created_at: datetime
    updated_at: datetime
    last_run: RunSummary | None = None


class DatasetListResponse(BaseModel):
    items: list[DatasetSummary]


class DatasetDetail(DatasetSummary):
    cases: list[CaseOut]


class RunCreate(BaseModel):
    retrieval_mode: Literal["question", "rewritten"] = "question"
    case_ids: list[uuid.UUID] | None = None
    retrieval_config: dict | None = None


class RunOut(BaseModel):
    id: uuid.UUID
    dataset_id: uuid.UUID
    dataset_name: str
    retrieval_mode: str
    status: str
    baseline_run_id: uuid.UUID | None
    total_items: int
    completed_items: int
    metrics: dict | None
    retrieval_config: dict | None = None
    error: str | None
    created_by: str
    started_at: datetime | None
    finished_at: datetime | None
    created_at: datetime
    progress: float


class RunListResponse(BaseModel):
    items: list[RunOut]


class RunItemOut(BaseModel):
    id: int
    case_id: uuid.UUID
    case_title: str
    turn_index: int
    question: str
    reference_answer: str | None
    expected_type: str
    required_document_ids: list[str]
    status: str
    retrieval_query: str | None
    retrieved: list | None
    citations: list | None
    answer: str | None
    judge_score: int | None
    judge_passed: bool | None
    refused: bool | None
    judge_reason: str | None
    retrieval_hit: bool | None
    retrieval_recall: float | None
    retrieval_rank: int | None
    citation_hit: bool | None
    citation_precision: float | None
    used_citation_hit: bool | None = None
    used_citation_precision: float | None = None
    invalid_refs: int = 0
    citation_fallback: bool = False
    rerank_degraded: bool = False
    passed: bool | None
    invalid_reason: str | None
    error: str | None
    latency_ms: int | None


class RunItemListResponse(BaseModel):
    items: list[RunItemOut]
    total: int
    page: int
    page_size: int


class CompareResponse(BaseModel):
    current: RunOut
    baseline: RunOut
    metric_delta: dict
    case_changes: dict


class PermissionOut(BaseModel):
    id: uuid.UUID
    username: str
    display_name: str
    role: str
    can_evaluate: bool


class PermissionListResponse(BaseModel):
    items: list[PermissionOut]


class PermissionUpdate(BaseModel):
    can_evaluate: bool
