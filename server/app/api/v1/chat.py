from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_user
from app.db.session import get_db
from app.models.user import User
from app.schemas.chat import ChatRequest
from app.services import rag_service

router = APIRouter(prefix="/chat", tags=["chat"])


@router.post("/stream")
async def chat_stream(
    payload: ChatRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> StreamingResponse:
    conversation, user_message = await rag_service.prepare_chat(
        db, user, payload.conversation_id, payload.message
    )
    return StreamingResponse(
        rag_service.stream_chat(
            user.id,
            conversation.id,
            user_message.id,
            payload.message,
        ),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
