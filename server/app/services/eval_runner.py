import logging
import time
import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import NullPool

from app.core.config import get_settings
from app.models.document import Document
from app.models.eval import EvalRun, EvalRunItem
from app.services import citations as citation_service
from app.services import eval_judge, llm_client, retrieval
from app.services.rag_service import _build_messages
from app.services.retrieval import RetrievalConfig

logger = logging.getLogger("app")
settings = get_settings()

REFUSAL_ANSWER = "根据现有知识库，我无法回答这个问题。"


async def _invalid_reason(
    db: AsyncSession, required_ids: list[str]
) -> str | None:
    if not required_ids:
        return None
    documents = (
        await db.execute(
            select(Document).where(
                Document.id.in_(
                    [uuid.UUID(item) for item in required_ids]
                )
            )
        )
    ).scalars().all()
    by_id = {str(document.id): document for document in documents}
    problems = []
    for doc_id in required_ids:
        document = by_id.get(doc_id)
        if not document or document.is_deleted:
            problems.append(f"{doc_id} 不存在或已删除")
        elif document.index_status != "ready":
            problems.append(
                f"{document.title} 索引状态为 {document.index_status}"
            )
    return "；".join(problems) if problems else None


async def _generate_answer(
    history: list[dict], question: str, context: str, citations: list
) -> str:
    mode = llm_client.provider()
    if mode == "deepseek":
        messages = _build_messages(history, question, context)
        parts: list[str] = []
        async for delta in llm_client.stream_deepseek(messages):
            parts.append(delta)
        return "".join(parts)
    parts = []
    async for delta in llm_client.stream_mock(citations):
        parts.append(delta)
    return "".join(parts)


async def _execute_item(
    db: AsyncSession,
    item: EvalRunItem,
    retrieval_mode: str,
    history: list[dict],
    config: RetrievalConfig,
) -> dict:
    question = item.question
    retrieval_query = question
    if retrieval_mode == "rewritten" and history:
        rewritten = await eval_judge.rewrite_question(history, question)
        if rewritten:
            retrieval_query = rewritten

    result = await retrieval.search(db, retrieval_query, config)
    items = result.items
    items = retrieval.merge_adjacent(items)
    items = retrieval.within_budget(items, config.context_token_budget)
    retrieved = [
        retrieval.to_citation(entry, index)
        for index, entry in enumerate(items, start=1)
    ]
    context = retrieval.build_context(items)
    if items:
        answer = await _generate_answer(history, question, context, retrieved)
    else:
        answer = REFUSAL_ANSWER
    used, citation_meta = citation_service.select_used(
        items, answer, settings.citation_required
    )
    citations = [
        retrieval.to_citation(entry, index) for index, entry in used
    ]

    required = [str(doc_id) for doc_id in (item.required_document_ids or [])]
    retrieved_ids = [entry["document_id"] for entry in retrieved]
    citation_ids = [entry["document_id"] for entry in citations]
    required_set = set(required)

    retrieval_hit = None
    retrieval_recall = None
    retrieval_rank = 0
    if required_set:
        matched = required_set & set(retrieved_ids)
        retrieval_hit = bool(matched)
        retrieval_recall = round(len(matched) / len(required_set), 4)
        for index, doc_id in enumerate(retrieved_ids, start=1):
            if doc_id in required_set:
                retrieval_rank = index
                break

    citation_hit = None
    citation_precision = None
    if required_set:
        cited = required_set & set(retrieved_ids)
        citation_hit = bool(cited)
        citation_precision = round(
            len(cited) / len(retrieved_ids), 4
        ) if retrieved_ids else 0.0

    used_citation_hit = None
    used_citation_precision = None
    if required_set:
        used_cited = required_set & set(citation_ids)
        used_citation_hit = bool(used_cited)
        used_citation_precision = round(
            len(used_cited) / len(citation_ids), 4
        ) if citation_ids else 0.0

    judge = await eval_judge.judge_turn(
        question,
        item.reference_answer,
        answer,
        item.expected_type,
        history,
    )

    if item.expected_type == "answerable":
        passed = bool(
            judge["score"] >= 4
            and (retrieval_hit is not False)
            and not judge["refused"]
        )
    else:
        passed = bool(judge["refused"])

    return {
        "retrieval_query": retrieval_query,
        "retrieved": retrieved,
        "citations": citations,
        "answer": answer,
        "judge_score": judge["score"],
        "judge_passed": bool(judge["passed"]),
        "refused": bool(judge["refused"]),
        "judge_reason": judge["reason"],
        "retrieval_hit": retrieval_hit,
        "retrieval_recall": retrieval_recall,
        "retrieval_rank": retrieval_rank,
        "citation_hit": citation_hit,
        "citation_precision": citation_precision,
        "used_citation_hit": used_citation_hit,
        "used_citation_precision": used_citation_precision,
        "invalid_refs": citation_meta.get("invalid_refs", 0),
        "citation_fallback": citation_meta.get("fallback", False),
        "rerank_degraded": result.degraded,
        "passed": passed,
    }


def _average(values: list[float]) -> float | None:
    if not values:
        return None
    return round(sum(values) / len(values), 4)


def _rate(numerator: int, denominator: int) -> float | None:
    if denominator == 0:
        return None
    return round(numerator / denominator, 4)


def aggregate_metrics(items: list[EvalRunItem]) -> dict:
    evaluated = [
        item for item in items if item.status in ("passed", "failed")
    ]
    answerable = [
        item for item in evaluated if item.expected_type == "answerable"
    ]
    unanswerable = [
        item for item in evaluated if item.expected_type == "unanswerable"
    ]
    scores = [
        item.judge_score
        for item in answerable
        if item.judge_score is not None
    ]
    recalls = [
        item.retrieval_recall
        for item in answerable
        if item.retrieval_recall is not None
    ]
    precisions = [
        item.citation_precision
        for item in answerable
        if item.citation_precision is not None
    ]
    used_precisions = [
        item.used_citation_precision
        for item in answerable
        if item.used_citation_precision is not None
    ]
    rr = [
        1 / item.retrieval_rank
        for item in answerable
        if item.retrieval_rank
    ]

    case_status: dict[str, list[bool]] = {}
    for item in evaluated:
        case_status.setdefault(str(item.case_id), []).append(
            bool(item.passed)
        )
    case_passed = sum(
        1 for results in case_status.values() if all(results)
    )

    latencies = [
        item.latency_ms
        for item in items
        if item.latency_ms is not None
    ]

    return {
        "total_items": len(items),
        "completed_items": sum(
            1 for item in items if item.status not in ("pending", "running")
        ),
        "valid_items": len(evaluated),
        "passed_items": sum(1 for item in evaluated if item.passed),
        "pass_rate": _rate(
            sum(1 for item in evaluated if item.passed), len(evaluated)
        ),
        "answerable_total": len(answerable),
        "answerable_passed": sum(
            1 for item in answerable if item.passed
        ),
        "answerable_pass_rate": _rate(
            sum(1 for item in answerable if item.passed), len(answerable)
        ),
        "answerable_avg_score": _average(scores),
        "answerable_retrieval_hit_rate": _rate(
            sum(1 for item in answerable if item.retrieval_hit), len(answerable)
        ),
        "answerable_avg_recall": _average(recalls),
        "answerable_mrr": _average(rr),
        "answerable_citation_hit_rate": _rate(
            sum(1 for item in answerable if item.citation_hit),
            len(answerable),
        ),
        "answerable_avg_citation_precision": _average(precisions),
        "answerable_used_citation_hit_rate": _rate(
            sum(1 for item in answerable if item.used_citation_hit),
            len(answerable),
        ),
        "answerable_avg_used_citation_precision": _average(
            used_precisions
        ),
        "invalid_refs_total": sum(
            item.invalid_refs or 0 for item in items
        ),
        "citation_fallback_rate": _rate(
            sum(1 for item in evaluated if item.citation_fallback),
            len(evaluated),
        ),
        "rerank_degraded_items": sum(
            1 for item in items if item.rerank_degraded
        ),
        "answerable_refused_rate": _rate(
            sum(1 for item in answerable if item.refused), len(answerable)
        ),
        "unanswerable_total": len(unanswerable),
        "unanswerable_refusal_rate": _rate(
            sum(1 for item in unanswerable if item.refused),
            len(unanswerable),
        ),
        "case_total": len(case_status),
        "case_passed": case_passed,
        "case_pass_rate": _rate(case_passed, len(case_status)),
        "invalid_items": sum(
            1 for item in items if item.status == "invalid"
        ),
        "error_items": sum(1 for item in items if item.status == "error"),
        "cancelled_items": sum(
            1 for item in items if item.status == "cancelled"
        ),
        "avg_latency_ms": _average([float(item) for item in latencies]),
    }


async def run_evaluation(run_id: str) -> None:
    run_uuid = uuid.UUID(run_id)
    engine = create_async_engine(settings.database_url, poolclass=NullPool)
    session_factory = async_sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False
    )
    try:
        async with session_factory() as db:
            run = await db.get(EvalRun, run_uuid)
            if not run or run.status not in ("pending", "running"):
                return
            run.status = "running"
            run.started_at = datetime.now(timezone.utc)
            await db.commit()

            config = RetrievalConfig.from_settings()
            if run.retrieval_config:
                config = RetrievalConfig(
                    **{**config.to_dict(), **run.retrieval_config}
                )

            items = (
                await db.execute(
                    select(EvalRunItem)
                    .where(EvalRunItem.run_id == run_uuid)
                    .order_by(EvalRunItem.id)
                )
            ).scalars().all()

            for item in items:
                reason = await _invalid_reason(
                    db, item.required_document_ids or []
                )
                if reason:
                    item.status = "invalid"
                    item.invalid_reason = reason
            await db.commit()

            history_by_case: dict[str, list[dict]] = {}
            cancelled = False

            for item in items:
                if item.status != "pending":
                    continue
                flag = (
                    await db.execute(
                        select(EvalRun.cancel_requested).where(
                            EvalRun.id == run_uuid
                        )
                    )
                ).scalar_one()
                if flag:
                    cancelled = True
                    break

                item.status = "running"
                await db.commit()
                started = time.monotonic()
                history = history_by_case.setdefault(
                    str(item.case_id), []
                )
                try:
                    result = await _execute_item(
                        db, item, run.retrieval_mode, history, config
                    )
                    for key, value in result.items():
                        setattr(item, key, value)
                    item.status = "passed" if result["passed"] else "failed"
                    history.append(
                        {"role": "user", "content": item.question}
                    )
                    history.append(
                        {"role": "assistant", "content": result["answer"]}
                    )
                except Exception as exc:
                    logger.exception("eval item failed")
                    item.status = "error"
                    item.error = f"{type(exc).__name__}: {exc}"[:1000]
                item.latency_ms = int(
                    (time.monotonic() - started) * 1000
                )
                run.completed_items = (run.completed_items or 0) + 1
                await db.commit()

            if cancelled:
                for item in items:
                    if item.status in ("pending", "running"):
                        item.status = "cancelled"

            run.status = "cancelled" if cancelled else "succeeded"
            run.finished_at = datetime.now(timezone.utc)
            run.metrics = aggregate_metrics(items)
            await db.commit()
    except Exception as exc:
        logger.exception("eval run failed")
        try:
            async with session_factory() as db:
                run = await db.get(EvalRun, run_uuid)
                if run:
                    run.status = "failed"
                    run.error = f"{type(exc).__name__}: {exc}"[:1000]
                    run.finished_at = datetime.now(timezone.utc)
                    await db.commit()
        except Exception:
            logger.exception("eval run failure status update failed")
        raise
    finally:
        await engine.dispose()
