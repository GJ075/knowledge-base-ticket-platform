import json
import uuid
from collections.abc import AsyncGenerator
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.errors import AppError
from app.db.session import SessionLocal
from app.models.conversation import Conversation, Message
from app.models.document import Document, DocumentChunk
from app.models.user import User
from app.schemas.chat import (
    Citation,
    ConversationDetail,
    ConversationListResponse,
    ConversationSummary,
    MessageOut,
)
from app.services import llm_client
from app.services.embedding_client import embed_query

settings = get_settings()

SYSTEM_PROMPT = """你是企业知识库助手。只能依据下面提供的资料回答；资料不足时，直接回答“根据现有知识库，我无法回答这个问题。”不要编造。回答使用中文。

资料：
{context}
"""


def sse(event: str, data: dict) -> str:
    return (
        f"event: {event}\n"
        f"data: {json.dumps(data, ensure_ascii=False)}\n\n"
    )


def _message_out(message: Message) -> MessageOut:
    citations = None
    if message.citations:
        citations = [Citation(**item) for item in message.citations]
    return MessageOut(
        id=message.id,
        role=message.role,
        content=message.content,
        citations=citations,
        created_at=message.created_at,
    )


async def list_conversations(
    db: AsyncSession,
    user_id: uuid.UUID,
    page: int,
    page_size: int,
) -> ConversationListResponse:
    page = max(page, 1)
    page_size = min(max(page_size, 1), 100)
    offset = (page - 1) * page_size
    total = (
        await db.execute(
            select(func.count())
            .select_from(Conversation)
            .where(Conversation.user_id == user_id)
        )
    ).scalar_one()
    conversations = (
        await db.execute(
            select(Conversation)
            .where(Conversation.user_id == user_id)
            .order_by(Conversation.updated_at.desc())
            .offset(offset)
            .limit(page_size)
        )
    ).scalars().all()
    return ConversationListResponse(
        items=[
            ConversationSummary(
                id=conversation.id,
                title=conversation.title,
                created_at=conversation.created_at,
                updated_at=conversation.updated_at,
            )
            for conversation in conversations
        ],
        total=total,
        page=page,
        page_size=page_size,
    )


async def get_conversation(
    db: AsyncSession,
    user_id: uuid.UUID,
    conversation_id: uuid.UUID,
) -> Conversation:
    conversation = (
        await db.execute(
            select(Conversation).where(
                Conversation.id == conversation_id,
                Conversation.user_id == user_id,
            )
        )
    ).scalar_one_or_none()
    if not conversation:
        raise AppError("NOT_FOUND", "会话不存在", 404)
    return conversation


async def conversation_detail(
    db: AsyncSession,
    user_id: uuid.UUID,
    conversation_id: uuid.UUID,
) -> ConversationDetail:
    conversation = await get_conversation(
        db, user_id, conversation_id
    )
    messages = (
        await db.execute(
            select(Message)
            .where(Message.conversation_id == conversation.id)
            .order_by(Message.created_at)
        )
    ).scalars().all()
    return ConversationDetail(
        id=conversation.id,
        title=conversation.title,
        created_at=conversation.created_at,
        updated_at=conversation.updated_at,
        messages=[_message_out(message) for message in messages],
    )


async def delete_conversation(
    db: AsyncSession,
    user_id: uuid.UUID,
    conversation_id: uuid.UUID,
) -> None:
    conversation = await get_conversation(
        db, user_id, conversation_id
    )
    await db.delete(conversation)
    await db.commit()


async def prepare_chat(
    db: AsyncSession,
    user: User,
    conversation_id: uuid.UUID | None,
    message: str,
) -> tuple[Conversation, Message]:
    if conversation_id:
        conversation = await get_conversation(
            db, user.id, conversation_id
        )
    else:
        title = message.strip()[:30] or "新对话"
        conversation = Conversation(user_id=user.id, title=title)
        db.add(conversation)
        await db.flush()

    user_message = Message(
        conversation_id=conversation.id,
        role="user",
        content=message,
    )
    db.add(user_message)
    conversation.updated_at = datetime.now(timezone.utc)
    await db.commit()
    return conversation, user_message


async def _load_history(
    db: AsyncSession,
    conversation_id: uuid.UUID,
    exclude_message_id: uuid.UUID,
) -> list[dict]:
    limit = max(settings.conversation_history_turns, 0) * 2
    if limit == 0:
        return []
    messages = (
        await db.execute(
            select(Message)
            .where(
                Message.conversation_id == conversation_id,
                Message.id != exclude_message_id,
            )
            .order_by(Message.created_at.desc())
            .limit(limit)
        )
    ).scalars().all()
    return [
        {"role": message.role, "content": message.content}
        for message in reversed(messages)
    ]


async def _search_chunks(
    db: AsyncSession,
    vector: list[float],
    top_k: int,
):
    return (
        await db.execute(
            select(DocumentChunk, Document)
            .join(Document, Document.id == DocumentChunk.document_id)
            .where(Document.is_deleted.is_(False))
            .order_by(DocumentChunk.embedding.cosine_distance(vector))
            .limit(top_k)
        )
    ).all()


def _citations(rows) -> list[dict]:
    return [
        {
            "document_id": str(document.id),
            "document_title": document.title,
            "chunk_index": chunk.chunk_index,
            "snippet": chunk.content[:300],
        }
        for chunk, document in rows
    ]


def _context(rows) -> str:
    lines = []
    for index, (chunk, document) in enumerate(rows, start=1):
        lines.append(
            f"[{index}] 文档《{document.title}》片段：{chunk.content}"
        )
    return "\n".join(lines)


def _build_messages(
    history: list[dict],
    question: str,
    context: str,
) -> list[dict]:
    messages = [
        {
            "role": "system",
            "content": SYSTEM_PROMPT.format(context=context),
        }
    ]
    messages.extend(history)
    messages.append({"role": "user", "content": question})
    return messages


async def _save_assistant(
    conversation_id: uuid.UUID,
    content: str,
    citations: list[dict],
) -> uuid.UUID:
    async with SessionLocal() as db:
        assistant = Message(
            conversation_id=conversation_id,
            role="assistant",
            content=content,
            citations=citations,
        )
        db.add(assistant)
        conversation = await db.get(Conversation, conversation_id)
        if conversation:
            conversation.updated_at = datetime.now(timezone.utc)
        await db.commit()
        return assistant.id


async def _stream_refusal(
    conversation_id: uuid.UUID,
) -> AsyncGenerator[str, None]:
    answer = "根据现有知识库，我无法回答这个问题。"
    for char in answer:
        yield sse("token", {"delta": char})
    assistant_id = await _save_assistant(conversation_id, answer, [])
    yield sse("done", {"assistant_message_id": str(assistant_id)})


async def stream_chat(
    user_id: uuid.UUID,
    conversation_id: uuid.UUID,
    user_message_id: uuid.UUID,
    question: str,
) -> AsyncGenerator[str, None]:
    try:
        yield sse(
            "meta",
            {
                "conversation_id": str(conversation_id),
                "user_message_id": str(user_message_id),
            },
        )

        async with SessionLocal() as db:
            history = await _load_history(
                db, conversation_id, user_message_id
            )
            try:
                vector = await embed_query(question)
            except Exception:
                yield sse(
                    "error",
                    {
                        "code": "EMBEDDING_UNAVAILABLE",
                        "message": "向量服务暂时不可用",
                    },
                )
                return
            rows = await _search_chunks(db, vector, settings.top_k)
            citations = _citations(rows)
            context = _context(rows)

        if not rows:
            async for chunk in _stream_refusal(conversation_id):
                yield chunk
            return

        yield sse("citations", {"items": citations})

        try:
            mode = llm_client.provider()
        except Exception as exc:
            yield sse(
                "error",
                {"code": "LLM_UNAVAILABLE", "message": str(exc)},
            )
            return

        messages = _build_messages(history, question, context)
        answer_parts: list[str] = []
        try:
            generator = (
                llm_client.stream_deepseek(messages)
                if mode == "deepseek"
                else llm_client.stream_mock(citations)
            )
            async for delta in generator:
                answer_parts.append(delta)
                yield sse("token", {"delta": delta})
        except Exception:
            yield sse(
                "error",
                {
                    "code": "LLM_UNAVAILABLE",
                    "message": "生成服务暂时不可用",
                },
            )
            return

        assistant_id = await _save_assistant(
            conversation_id,
            "".join(answer_parts),
            citations,
        )
        yield sse("done", {"assistant_message_id": str(assistant_id)})
    except Exception:
        yield sse(
            "error",
            {"code": "INTERNAL_ERROR", "message": "对话处理失败"},
        )
