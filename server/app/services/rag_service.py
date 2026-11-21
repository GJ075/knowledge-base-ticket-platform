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
from app.models.user import User
from app.schemas.chat import (
    Citation,
    ConversationDetail,
    ConversationListResponse,
    ConversationSummary,
    MessageOut,
)
from app.services import citations as citation_service
from app.services import eval_judge, llm_client, retrieval
from app.services.retrieval import RetrievalConfig, Retrieved

settings = get_settings()

SYSTEM_PROMPT = """你是企业知识库助手。只能依据下面提供的资料回答；资料不足时，直接回答“根据现有知识库，我无法回答这个问题。”不要编造。回答使用中文。

每条结论后用方括号标注资料编号，例如 [1]、[2]；只能引用下列资料中存在的编号，不要编造编号。

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
        citation_meta=message.citation_meta,
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


async def recompute_citations(
    db: AsyncSession,
    user_id: uuid.UUID,
    conversation_id: uuid.UUID,
    limit: int = 10,
) -> dict:
    """Recompute candidate citations for legacy messages without meta.

    Old answers have no inline markers, so true usage cannot be recovered;
    the returned citations are threshold-filtered candidates labelled as
    recomputed. Stored messages are not modified.
    """
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

    pairs: list[tuple[Message, Message | None]] = []
    previous_user: Message | None = None
    for message in messages:
        if message.role == "user":
            previous_user = message
        elif message.role == "assistant" and not message.citation_meta:
            pairs.append((message, previous_user))
    pairs = [pair for pair in pairs if pair[1]][-limit:]

    config = RetrievalConfig.from_settings()
    items: list[dict] = []
    for assistant, user_message in pairs:
        try:
            result = await retrieval.search(
                db, user_message.content, config
            )
        except Exception:
            continue
        kept = retrieval.merge_adjacent(result.items)
        kept = retrieval.within_budget(
            kept, config.context_token_budget
        )
        items.append(
            {
                "message_id": str(assistant.id),
                "mode": "recomputed",
                "degraded": result.degraded,
                "citations": [
                    retrieval.to_citation(item, index)
                    for index, item in enumerate(kept, start=1)
                ],
            }
        )
    return {"items": items}


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


def _citations(items: list[Retrieved]) -> list[dict]:
    return [
        retrieval.to_citation(item, index)
        for index, item in enumerate(items, start=1)
    ]


def _context(items: list[Retrieved]) -> str:
    return retrieval.build_context(items)


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
    meta: dict | None = None,
) -> uuid.UUID:
    async with SessionLocal() as db:
        assistant = Message(
            conversation_id=conversation_id,
            role="assistant",
            content=content,
            citations=citations,
            citation_meta=meta,
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
    yield sse("citations", {"items": []})
    for char in answer:
        yield sse("token", {"delta": char})
    yield sse(
        "used_citations",
        {"items": [], "fallback": False, "invalid_refs": 0},
    )
    assistant_id = await _save_assistant(
        conversation_id,
        answer,
        [],
        {"mode": "empty", "candidate_count": 0, "fallback": False},
    )
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
            config = RetrievalConfig.from_settings()
            search_query = question
            if config.rewrite_enabled and history:
                rewritten = await eval_judge.rewrite_question(
                    history, question
                )
                if rewritten:
                    search_query = rewritten
            try:
                result = await retrieval.search(db, search_query, config)
            except Exception:
                yield sse(
                    "error",
                    {
                        "code": "EMBEDDING_UNAVAILABLE",
                        "message": "向量服务暂时不可用",
                    },
                )
                return
            items = result.items
            items = retrieval.merge_adjacent(items)
            items = retrieval.within_budget(
                items, config.context_token_budget
            )
            citations = _citations(items)
            context = _context(items)

        if not items:
            async for chunk in _stream_refusal(conversation_id):
                yield chunk
            return

        yield sse(
            "citations",
            {
                "items": citations,
                "threshold": config.rerank_threshold,
                "delta": config.rerank_delta,
                "degraded": result.degraded,
            },
        )

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

        answer = "".join(answer_parts)
        used, meta = citation_service.select_used(
            items, answer, settings.citation_required
        )
        used_citations = [
            retrieval.to_citation(item, index)
            for index, item in used
        ]
        meta["degraded"] = result.degraded
        yield sse(
            "used_citations",
            {
                "items": used_citations,
                "fallback": meta["fallback"],
                "invalid_refs": meta["invalid_refs"],
                "degraded": result.degraded,
            },
        )
        assistant_id = await _save_assistant(
            conversation_id,
            answer,
            used_citations,
            meta,
        )
        yield sse("done", {"assistant_message_id": str(assistant_id)})
    except Exception:
        yield sse(
            "error",
            {"code": "INTERNAL_ERROR", "message": "对话处理失败"},
        )
