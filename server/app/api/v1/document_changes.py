from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_user, require_leader
from app.db.session import get_db
from app.models.user import User
from app.schemas.document import (
    BatchIdsResponse,
    BatchRejectRequest,
    BatchReviewRequest,
    DocumentActionResponse,
    DocumentChangeListResponse,
    DocumentChangeOut,
    RejectRequest,
    ReviewRequest,
)
from app.services import document_service

router = APIRouter(prefix="/document-changes", tags=["document-changes"])


@router.get("", response_model=DocumentChangeListResponse)
async def list_changes(
    status: str | None = Query(default=None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> DocumentChangeListResponse:
    return await document_service.list_changes(
        db, user, status, page, page_size
    )


@router.post(
    "/batch-approve", response_model=BatchIdsResponse
)
async def batch_approve(
    payload: BatchReviewRequest,
    db: AsyncSession = Depends(get_db),
    reviewer: User = Depends(require_leader),
) -> BatchIdsResponse:
    return await document_service.batch_review(
        db, reviewer, payload.ids, payload.comment, approve=True
    )


@router.post("/batch-reject", response_model=BatchIdsResponse)
async def batch_reject(
    payload: BatchRejectRequest,
    db: AsyncSession = Depends(get_db),
    reviewer: User = Depends(require_leader),
) -> BatchIdsResponse:
    return await document_service.batch_review(
        db, reviewer, payload.ids, payload.comment, approve=False
    )


@router.get("/{change_id}", response_model=DocumentChangeOut)
async def get_change(
    change_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> DocumentChangeOut:
    return await document_service.change_detail(db, user, change_id)


@router.post(
    "/{change_id}/approve", response_model=DocumentActionResponse
)
async def approve_change(
    change_id: UUID,
    payload: ReviewRequest,
    db: AsyncSession = Depends(get_db),
    reviewer: User = Depends(require_leader),
) -> DocumentActionResponse:
    return await document_service.approve_change(
        db, reviewer, change_id, payload.comment
    )


@router.post(
    "/{change_id}/reject", response_model=DocumentActionResponse
)
async def reject_change(
    change_id: UUID,
    payload: RejectRequest,
    db: AsyncSession = Depends(get_db),
    reviewer: User = Depends(require_leader),
) -> DocumentActionResponse:
    return await document_service.reject_change(
        db, reviewer, change_id, payload.comment
    )
