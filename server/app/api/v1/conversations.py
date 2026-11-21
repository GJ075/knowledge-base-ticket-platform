from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_user
from app.db.session import get_db
from app.models.user import User
from app.schemas.chat import (
    ConversationDetail,
    ConversationListResponse,
    RecitationResponse,
)
from app.services import rag_service

router = APIRouter(prefix="/conversations", tags=["conversations"])


@router.get("", response_model=ConversationListResponse)
async def list_conversations(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> ConversationListResponse:
    return await rag_service.list_conversations(
        db, user.id, page, page_size
    )


@router.get("/{conversation_id}", response_model=ConversationDetail)
async def get_conversation(
    conversation_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> ConversationDetail:
    return await rag_service.conversation_detail(
        db, user.id, conversation_id
    )


@router.get(
    "/{conversation_id}/recitations",
    response_model=RecitationResponse,
)
async def recompute_citations(
    conversation_id: UUID,
    limit: int = Query(10, ge=1, le=50),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> RecitationResponse:
    return RecitationResponse(
        **await rag_service.recompute_citations(
            db, user.id, conversation_id, limit
        )
    )


@router.delete("/{conversation_id}", status_code=204)
async def delete_conversation(
    conversation_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> None:
    await rag_service.delete_conversation(
        db, user.id, conversation_id
    )
