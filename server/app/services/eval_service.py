import json
import uuid

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.errors import AppError
from app.models.document import Document
from app.models.eval import (
    EvalCase,
    EvalDataset,
    EvalRun,
    EvalRunItem,
    EvalTurn,
)
from app.models.user import User
from app.schemas.eval import (
    CaseIn,
    CaseOut,
    CaseUpdate,
    CompareResponse,
    DatasetDetail,
    DatasetSummary,
    DocumentRef,
    RunItemListResponse,
    RunItemOut,
    RunListResponse,
    RunOut,
    RunSummary,
    TurnIn,
    TurnOut,
)
from app.services.retrieval import RetrievalConfig

MAX_TURNS = 5


def _merge_retrieval_config(override: dict | None) -> dict:
    base = RetrievalConfig.from_settings().to_dict()
    if not override:
        return base
    merged = dict(base)
    for key, value in override.items():
        if key not in base:
            continue
        default = base[key]
        if isinstance(default, bool):
            merged[key] = str(value).lower() in {"1", "true", "yes"}
            continue
        try:
            merged[key] = type(default)(value)
        except (TypeError, ValueError):
            continue
    try:
        return RetrievalConfig(**merged).to_dict()
    except ValueError as exc:
        raise AppError("VALIDATION_ERROR", str(exc), 422) from exc


def _validate_turn_shape(payload: TurnIn) -> None:
    if payload.expected_type == "answerable":
        if not (payload.reference_answer or "").strip():
            raise AppError(
                "EVAL_CASE_INVALID", "可回答轮次必须填写参考答案", 422
            )
        if not payload.required_document_ids:
            raise AppError(
                "EVAL_CASE_INVALID", "可回答轮次必须至少指定一个必引文档",
                422,
            )


async def _validate_turn_documents(
    db: AsyncSession, payload: TurnIn
) -> list[str]:
    _validate_turn_shape(payload)
    ids = list(
        dict.fromkeys(str(item) for item in payload.required_document_ids)
    )
    if not ids:
        return []
    documents = (
        await db.execute(
            select(Document).where(
                Document.id.in_([uuid.UUID(item) for item in ids]),
                Document.is_deleted.is_(False),
            )
        )
    ).scalars().all()
    found = {str(document.id) for document in documents}
    missing = [item for item in ids if item not in found]
    if missing:
        raise AppError(
            "EVAL_CASE_INVALID",
            "必引文档不存在或已删除：" + ", ".join(missing),
            422,
        )
    return ids


def _case_out(case: EvalCase, titles: dict[str, str]) -> CaseOut:
    def turn_out(turn: EvalTurn) -> TurnOut:
        doc_ids = list(dict.fromkeys(turn.required_document_ids or []))
        return TurnOut(
            id=turn.id,
            turn_index=turn.turn_index,
            question=turn.question,
            reference_answer=turn.reference_answer,
            expected_type=turn.expected_type,
            required_document_ids=doc_ids,
            required_documents=[
                DocumentRef(id=uuid.UUID(doc_id), title=titles[doc_id])
                for doc_id in doc_ids
                if doc_id in titles
            ],
        )

    return CaseOut(
        id=case.id,
        title=case.title,
        tags=case.tags or [],
        sort_order=case.sort_order,
        turns=[turn_out(turn) for turn in case.turns],
    )


async def _document_titles(
    db: AsyncSession, cases: list[EvalCase]
) -> dict[str, str]:
    ids = {
        doc_id
        for case in cases
        for turn in case.turns
        for doc_id in (turn.required_document_ids or [])
    }
    if not ids:
        return {}
    documents = (
        await db.execute(
            select(Document).where(
                Document.id.in_([uuid.UUID(item) for item in ids])
            )
        )
    ).scalars().all()
    return {str(document.id): document.title for document in documents}


async def _run_summary(db: AsyncSession, dataset_id: uuid.UUID):
    run = (
        await db.execute(
            select(EvalRun)
            .where(EvalRun.dataset_id == dataset_id)
            .order_by(EvalRun.created_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    if not run:
        return None
    return RunSummary(
        id=run.id,
        status=run.status,
        retrieval_mode=run.retrieval_mode,
        total_items=run.total_items,
        completed_items=run.completed_items,
        created_at=run.created_at,
        finished_at=run.finished_at,
    )


async def _dataset_summary(
    db: AsyncSession, dataset: EvalDataset
) -> DatasetSummary:
    case_count = (
        await db.execute(
            select(func.count())
            .select_from(EvalCase)
            .where(EvalCase.dataset_id == dataset.id)
        )
    ).scalar_one()
    turn_count = (
        await db.execute(
            select(func.count())
            .select_from(EvalTurn)
            .join(EvalCase, EvalCase.id == EvalTurn.case_id)
            .where(EvalCase.dataset_id == dataset.id)
        )
    ).scalar_one()
    return DatasetSummary(
        id=dataset.id,
        name=dataset.name,
        description=dataset.description,
        is_archived=dataset.is_archived,
        case_count=case_count,
        turn_count=turn_count,
        created_at=dataset.created_at,
        updated_at=dataset.updated_at,
        last_run=await _run_summary(db, dataset.id),
    )


async def list_datasets(
    db: AsyncSession, include_archived: bool = False
) -> list[DatasetSummary]:
    query = select(EvalDataset).order_by(EvalDataset.updated_at.desc())
    if not include_archived:
        query = query.where(EvalDataset.is_archived.is_(False))
    datasets = (await db.execute(query)).scalars().all()
    return [await _dataset_summary(db, item) for item in datasets]


async def _get_dataset(
    db: AsyncSession, dataset_id: uuid.UUID
) -> EvalDataset:
    dataset = await db.get(EvalDataset, dataset_id)
    if not dataset:
        raise AppError("NOT_FOUND", "数据集不存在", 404)
    return dataset


async def create_dataset(
    db: AsyncSession,
    user: User,
    name: str,
    description: str | None,
) -> DatasetSummary:
    name = name.strip()
    existing = (
        await db.execute(select(EvalDataset).where(EvalDataset.name == name))
    ).scalar_one_or_none()
    if existing:
        raise AppError("EVAL_DATASET_EXISTS", "数据集名称已存在", 409)
    dataset = EvalDataset(
        name=name, description=description, created_by=user.id
    )
    db.add(dataset)
    await db.commit()
    await db.refresh(dataset)
    return await _dataset_summary(db, dataset)


async def update_dataset(
    db: AsyncSession,
    dataset_id: uuid.UUID,
    name: str | None,
    description: str | None,
) -> DatasetSummary:
    dataset = await _get_dataset(db, dataset_id)
    if name is not None:
        name = name.strip()
        duplicate = (
            await db.execute(
                select(EvalDataset).where(
                    EvalDataset.name == name,
                    EvalDataset.id != dataset_id,
                )
            )
        ).scalar_one_or_none()
        if duplicate:
            raise AppError(
                "EVAL_DATASET_EXISTS", "数据集名称已存在", 409
            )
        dataset.name = name
    if description is not None:
        dataset.description = description
    await db.commit()
    await db.refresh(dataset)
    return await _dataset_summary(db, dataset)


async def archive_dataset(
    db: AsyncSession, dataset_id: uuid.UUID
) -> DatasetSummary:
    dataset = await _get_dataset(db, dataset_id)
    dataset.is_archived = True
    await db.commit()
    await db.refresh(dataset)
    return await _dataset_summary(db, dataset)


async def dataset_detail(
    db: AsyncSession, dataset_id: uuid.UUID
) -> DatasetDetail:
    dataset = await _get_dataset(db, dataset_id)
    cases = (
        await db.execute(
            select(EvalCase)
            .where(EvalCase.dataset_id == dataset_id)
            .order_by(EvalCase.sort_order, EvalCase.created_at)
        )
    ).scalars().all()
    titles = await _document_titles(db, cases)
    summary = await _dataset_summary(db, dataset)
    return DatasetDetail(
        **summary.model_dump(),
        cases=[_case_out(case, titles) for case in cases],
    )


async def _get_case(db: AsyncSession, case_id: uuid.UUID) -> EvalCase:
    case = await db.get(EvalCase, case_id)
    if not case:
        raise AppError("NOT_FOUND", "用例不存在", 404)
    return case


async def _reload_case(db: AsyncSession, case_id: uuid.UUID) -> EvalCase:
    return (
        await db.execute(
            select(EvalCase)
            .where(EvalCase.id == case_id)
            .options(selectinload(EvalCase.turns))
            .execution_options(populate_existing=True)
        )
    ).scalar_one()


async def create_case(
    db: AsyncSession, dataset_id: uuid.UUID, payload: CaseIn
) -> CaseOut:
    await _get_dataset(db, dataset_id)
    document_ids: list[list[str]] = []
    for turn in payload.turns:
        document_ids.append(await _validate_turn_documents(db, turn))
    max_order = (
        await db.execute(
            select(func.coalesce(func.max(EvalCase.sort_order), 0)).where(
                EvalCase.dataset_id == dataset_id
            )
        )
    ).scalar_one()
    case = EvalCase(
        dataset_id=dataset_id,
        title=payload.title.strip(),
        tags=payload.tags,
        sort_order=int(max_order) + 1,
    )
    db.add(case)
    await db.flush()
    for index, (turn, ids) in enumerate(
        zip(payload.turns, document_ids), start=1
    ):
        db.add(
            EvalTurn(
                case_id=case.id,
                turn_index=index,
                question=turn.question.strip(),
                reference_answer=(turn.reference_answer or None),
                expected_type=turn.expected_type,
                required_document_ids=ids,
            )
        )
    await db.commit()
    case = await _reload_case(db, case.id)
    titles = await _document_titles(db, [case])
    return _case_out(case, titles)


async def update_case(
    db: AsyncSession, case_id: uuid.UUID, payload: CaseUpdate
) -> CaseOut:
    case = await _get_case(db, case_id)
    if payload.title is not None:
        case.title = payload.title.strip()
    if payload.tags is not None:
        case.tags = payload.tags
    await db.commit()
    titles = await _document_titles(db, [case])
    return _case_out(case, titles)


async def delete_case(db: AsyncSession, case_id: uuid.UUID) -> None:
    case = await _get_case(db, case_id)
    await db.delete(case)
    await db.commit()


async def replace_case(
    db: AsyncSession, case_id: uuid.UUID, payload: CaseIn
) -> CaseOut:
    case = await _get_case(db, case_id)
    resolved_turns: list[list[str]] = []
    for turn in payload.turns:
        resolved_turns.append(await _validate_turn_documents(db, turn))
    case.title = payload.title.strip()
    case.tags = payload.tags
    await db.execute(delete(EvalTurn).where(EvalTurn.case_id == case_id))
    await db.flush()
    for index, (turn, ids) in enumerate(
        zip(payload.turns, resolved_turns), start=1
    ):
        db.add(
            EvalTurn(
                case_id=case_id,
                turn_index=index,
                question=turn.question.strip(),
                reference_answer=(turn.reference_answer or None),
                expected_type=turn.expected_type,
                required_document_ids=ids,
            )
        )
    await db.commit()
    case = await _reload_case(db, case_id)
    titles = await _document_titles(db, [case])
    return _case_out(case, titles)


async def create_turn(
    db: AsyncSession, case_id: uuid.UUID, payload: TurnIn
) -> CaseOut:
    case = await _get_case(db, case_id)
    ids = await _validate_turn_documents(db, payload)
    current = (
        await db.execute(
            select(func.coalesce(func.max(EvalTurn.turn_index), 0)).where(
                EvalTurn.case_id == case_id
            )
        )
    ).scalar_one()
    if int(current) >= MAX_TURNS:
        raise AppError(
            "EVAL_CASE_INVALID", "单个用例最多 5 轮", 422
        )
    db.add(
        EvalTurn(
            case_id=case_id,
            turn_index=int(current) + 1,
            question=payload.question.strip(),
            reference_answer=(payload.reference_answer or None),
            expected_type=payload.expected_type,
            required_document_ids=ids,
        )
    )
    await db.commit()
    case = await _reload_case(db, case_id)
    titles = await _document_titles(db, [case])
    return _case_out(case, titles)


async def update_turn(
    db: AsyncSession, turn_id: uuid.UUID, payload: TurnIn
) -> CaseOut:
    turn = await db.get(EvalTurn, turn_id)
    if not turn:
        raise AppError("NOT_FOUND", "轮次不存在", 404)
    ids = await _validate_turn_documents(db, payload)
    turn.question = payload.question.strip()
    turn.reference_answer = payload.reference_answer or None
    turn.expected_type = payload.expected_type
    turn.required_document_ids = ids
    await db.commit()
    case = await _reload_case(db, turn.case_id)
    titles = await _document_titles(db, [case])
    return _case_out(case, titles)


async def delete_turn(db: AsyncSession, turn_id: uuid.UUID) -> CaseOut:
    turn = await db.get(EvalTurn, turn_id)
    if not turn:
        raise AppError("NOT_FOUND", "轮次不存在", 404)
    case_id = turn.case_id
    case = await _get_case(db, case_id)
    if len(case.turns) <= 1:
        raise AppError(
            "EVAL_CASE_INVALID", "用例至少保留一个轮次", 422
        )
    await db.delete(turn)
    await db.flush()
    remaining = (
        await db.execute(
            select(EvalTurn)
            .where(EvalTurn.case_id == case_id)
            .order_by(EvalTurn.turn_index)
        )
    ).scalars().all()
    for index, item in enumerate(remaining, start=1):
        item.turn_index = index
    await db.commit()
    case = await _reload_case(db, case_id)
    titles = await _document_titles(db, [case])
    return _case_out(case, titles)


async def _resolve_titles(
    db: AsyncSession, titles: list[str]
) -> list[str]:
    if not titles:
        return []
    documents = (
        await db.execute(
            select(Document).where(
                Document.title.in_(titles), Document.is_deleted.is_(False)
            )
        )
    ).scalars().all()
    by_title: dict[str, list[Document]] = {}
    for document in documents:
        by_title.setdefault(document.title, []).append(document)
    resolved: list[str] = []
    for title in titles:
        matches = by_title.get(title, [])
        if len(matches) != 1:
            raise AppError(
                "EVAL_IMPORT_ERROR",
                f"必引文档《{title}》不存在或标题重复",
                422,
            )
        resolved.append(str(matches[0].id))
    return list(dict.fromkeys(resolved))


async def import_jsonl(
    db: AsyncSession, user: User, content: str
) -> dict:
    lines = [line.strip() for line in content.splitlines() if line.strip()]
    if not lines:
        raise AppError("EVAL_IMPORT_ERROR", "文件为空", 422)
    try:
        header = json.loads(lines[0])
    except json.JSONDecodeError as exc:
        raise AppError(
            "EVAL_IMPORT_ERROR", f"第 1 行不是合法 JSON：{exc}", 422
        )
    if header.get("type") != "dataset" or not header.get("name"):
        raise AppError(
            "EVAL_IMPORT_ERROR", "第 1 行必须是数据集元信息", 422
        )
    name = str(header["name"]).strip()[:100]
    existing = (
        await db.execute(select(EvalDataset).where(EvalDataset.name == name))
    ).scalar_one_or_none()
    if existing:
        raise AppError("EVAL_DATASET_EXISTS", "数据集名称已存在", 409)

    parsed: list[tuple[dict, list[list[str]]]] = []
    for offset, line in enumerate(lines[1:], start=2):
        try:
            row = json.loads(line)
        except json.JSONDecodeError as exc:
            raise AppError(
                "EVAL_IMPORT_ERROR", f"第 {offset} 行不是合法 JSON：{exc}",
                422,
            )
        if row.get("type") != "case":
            raise AppError(
                "EVAL_IMPORT_ERROR", f"第 {offset} 行 type 必须是 case", 422
            )
        title = str(row.get("title") or "").strip()
        if not title:
            raise AppError(
                "EVAL_IMPORT_ERROR", f"第 {offset} 行缺少标题", 422
            )
        turns = row.get("turns") or []
        if not 1 <= len(turns) <= MAX_TURNS:
            raise AppError(
                "EVAL_IMPORT_ERROR",
                f"第 {offset} 行轮次数必须在 1–{MAX_TURNS} 之间",
                422,
            )
        resolved_turns: list[list[str]] = []
        for turn in turns:
            expected_type = turn.get("expected_type", "answerable")
            if expected_type not in ("answerable", "unanswerable"):
                raise AppError(
                    "EVAL_IMPORT_ERROR",
                    f"第 {offset} 行 expected_type 非法", 422,
                )
            if expected_type == "answerable":
                if not (turn.get("reference_answer") or "").strip():
                    raise AppError(
                        "EVAL_IMPORT_ERROR",
                        f"第 {offset} 行可回答轮次缺少参考答案", 422,
                    )
                if not (turn.get("required_document_titles") or []):
                    raise AppError(
                        "EVAL_IMPORT_ERROR",
                        f"第 {offset} 行可回答轮次缺少必引文档", 422,
                    )
            try:
                resolved_turns.append(
                    await _resolve_titles(
                        db, turn.get("required_document_titles") or []
                    )
                )
            except AppError as exc:
                raise AppError(
                    "EVAL_IMPORT_ERROR", f"第 {offset} 行：{exc.message}", 422
                )
        parsed.append((row, resolved_turns))

    if not parsed:
        raise AppError("EVAL_IMPORT_ERROR", "没有可导入的用例", 422)

    dataset = EvalDataset(
        name=name,
        description=header.get("description"),
        created_by=user.id,
    )
    db.add(dataset)
    await db.flush()
    turn_total = 0
    for order, (row, resolved_turns) in enumerate(parsed, start=1):
        case = EvalCase(
            dataset_id=dataset.id,
            title=str(row["title"]).strip()[:255],
            tags=[str(tag) for tag in (row.get("tags") or [])],
            sort_order=order,
        )
        db.add(case)
        await db.flush()
        for index, (turn, ids) in enumerate(
            zip(row["turns"], resolved_turns), start=1
        ):
            db.add(
                EvalTurn(
                    case_id=case.id,
                    turn_index=index,
                    question=str(turn.get("question") or "").strip(),
                    reference_answer=turn.get("reference_answer"),
                    expected_type=turn.get("expected_type", "answerable"),
                    required_document_ids=ids,
                )
            )
            turn_total += 1
    await db.commit()
    return {
        "dataset_id": str(dataset.id),
        "imported_cases": len(parsed),
        "imported_turns": turn_total,
    }


async def export_jsonl(db: AsyncSession, dataset_id: uuid.UUID) -> str:
    detail = await dataset_detail(db, dataset_id)
    lines = [
        json.dumps(
            {
                "type": "dataset",
                "name": detail.name,
                "description": detail.description,
            },
            ensure_ascii=False,
        )
    ]
    for case in detail.cases:
        lines.append(
            json.dumps(
                {
                    "type": "case",
                    "title": case.title,
                    "tags": case.tags,
                    "turns": [
                        {
                            "question": turn.question,
                            "reference_answer": turn.reference_answer,
                            "expected_type": turn.expected_type,
                            "required_document_titles": [
                                document.title
                                for document in turn.required_documents
                            ],
                        }
                        for turn in case.turns
                    ],
                },
                ensure_ascii=False,
            )
        )
    return "\n".join(lines) + "\n"


def _run_out(run: EvalRun, dataset_name: str, creator: str) -> RunOut:
    progress = (
        round(run.completed_items / run.total_items, 4)
        if run.total_items
        else 0.0
    )
    return RunOut(
        id=run.id,
        dataset_id=run.dataset_id,
        dataset_name=dataset_name,
        retrieval_mode=run.retrieval_mode,
        status=run.status,
        baseline_run_id=run.baseline_run_id,
        total_items=run.total_items,
        completed_items=run.completed_items,
        metrics=run.metrics,
        retrieval_config=run.retrieval_config,
        error=run.error,
        created_by=creator,
        started_at=run.started_at,
        finished_at=run.finished_at,
        created_at=run.created_at,
        progress=progress,
    )


async def _run_out_one(db: AsyncSession, run: EvalRun) -> RunOut:
    dataset = await db.get(EvalDataset, run.dataset_id)
    creator = await db.get(User, run.created_by)
    return _run_out(
        run,
        dataset.name if dataset else "",
        creator.display_name if creator else "",
    )


async def create_run(
    db: AsyncSession,
    user: User,
    dataset_id: uuid.UUID,
    retrieval_mode: str,
    case_ids: list[uuid.UUID] | None = None,
    retrieval_config: dict | None = None,
) -> RunOut:
    dataset = await _get_dataset(db, dataset_id)
    running = (
        await db.execute(
            select(EvalRun).where(
                EvalRun.dataset_id == dataset_id,
                EvalRun.status.in_(("pending", "running")),
            )
        )
    ).scalar_one_or_none()
    if running:
        raise AppError(
            "EVAL_RUN_IN_PROGRESS", "该数据集已有运行中的评测", 409
        )

    cases = (
        await db.execute(
            select(EvalCase)
            .where(EvalCase.dataset_id == dataset_id)
            .order_by(EvalCase.sort_order, EvalCase.created_at)
        )
    ).scalars().all()
    if case_ids is not None:
        if not case_ids:
            raise AppError(
                "EVAL_CASE_INVALID", "请至少选择一个用例", 422
            )
        wanted = {str(case_id) for case_id in case_ids}
        known = {str(case.id) for case in cases}
        if wanted - known:
            raise AppError(
                "EVAL_CASE_INVALID",
                "存在不属于该数据集的用例",
                422,
            )
        cases = [case for case in cases if str(case.id) in wanted]
    items: list[EvalRunItem] = []
    for case in cases:
        for turn in case.turns:
            items.append(
                EvalRunItem(
                    run_id=None,
                    case_id=case.id,
                    case_title=case.title,
                    turn_index=turn.turn_index,
                    question=turn.question,
                    reference_answer=turn.reference_answer,
                    expected_type=turn.expected_type,
                    required_document_ids=turn.required_document_ids or [],
                )
            )
    if not items:
        raise AppError("EVAL_DATASET_EMPTY", "数据集没有可运行用例", 422)

    run = EvalRun(
        dataset_id=dataset.id,
        retrieval_mode=retrieval_mode,
        status="pending",
        created_by=user.id,
        total_items=len(items),
        retrieval_config=_merge_retrieval_config(retrieval_config),
    )
    db.add(run)
    await db.flush()
    for item in items:
        item.run_id = run.id
    db.add_all(items)
    await db.commit()
    await db.refresh(run)

    from app.tasks.evaluation import run_evaluation_task

    run_evaluation_task.delay(str(run.id))
    return _run_out(run, dataset.name, user.display_name)


async def list_runs(
    db: AsyncSession, dataset_id: uuid.UUID | None, limit: int = 50
) -> RunListResponse:
    query = (
        select(EvalRun).order_by(EvalRun.created_at.desc()).limit(limit)
    )
    if dataset_id:
        query = query.where(EvalRun.dataset_id == dataset_id)
    runs = (await db.execute(query)).scalars().all()
    return RunListResponse(
        items=[await _run_out_one(db, run) for run in runs]
    )


async def run_detail(db: AsyncSession, run_id: uuid.UUID) -> RunOut:
    run = await db.get(EvalRun, run_id)
    if not run:
        raise AppError("NOT_FOUND", "评测运行不存在", 404)
    return await _run_out_one(db, run)


async def list_run_items(
    db: AsyncSession,
    run_id: uuid.UUID,
    status: str | None,
    page: int,
    page_size: int,
) -> RunItemListResponse:
    run = await db.get(EvalRun, run_id)
    if not run:
        raise AppError("NOT_FOUND", "评测运行不存在", 404)
    base = select(EvalRunItem).where(EvalRunItem.run_id == run_id)
    count_query = select(func.count()).select_from(EvalRunItem).where(
        EvalRunItem.run_id == run_id
    )
    if status:
        base = base.where(EvalRunItem.status == status)
        count_query = count_query.where(EvalRunItem.status == status)
    total = (await db.execute(count_query)).scalar_one()
    items = (
        await db.execute(
            base.order_by(
                EvalRunItem.case_title, EvalRunItem.turn_index
            )
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    ).scalars().all()
    return RunItemListResponse(
        items=[
            RunItemOut(
                id=item.id,
                case_id=item.case_id,
                case_title=item.case_title,
                turn_index=item.turn_index,
                question=item.question,
                reference_answer=item.reference_answer,
                expected_type=item.expected_type,
                required_document_ids=item.required_document_ids or [],
                status=item.status,
                retrieval_query=item.retrieval_query,
                retrieved=item.retrieved,
                citations=item.citations,
                answer=item.answer,
                judge_score=item.judge_score,
                judge_passed=item.judge_passed,
                refused=item.refused,
                judge_reason=item.judge_reason,
                retrieval_hit=item.retrieval_hit,
                retrieval_recall=item.retrieval_recall,
                retrieval_rank=item.retrieval_rank,
                citation_hit=item.citation_hit,
                citation_precision=item.citation_precision,
                used_citation_hit=item.used_citation_hit,
                used_citation_precision=item.used_citation_precision,
                invalid_refs=item.invalid_refs,
                citation_fallback=item.citation_fallback,
                rerank_degraded=item.rerank_degraded,
                passed=item.passed,
                invalid_reason=item.invalid_reason,
                error=item.error,
                latency_ms=item.latency_ms,
            )
            for item in items
        ],
        total=total,
        page=page,
        page_size=page_size,
    )


async def cancel_run(db: AsyncSession, run_id: uuid.UUID) -> RunOut:
    run = await db.get(EvalRun, run_id)
    if not run:
        raise AppError("NOT_FOUND", "评测运行不存在", 404)
    if run.status not in ("pending", "running"):
        raise AppError(
            "EVAL_RUN_NOT_ACTIVE", "该运行已结束，无法取消", 409
        )
    run.cancel_requested = True
    await db.commit()
    await db.refresh(run)
    return await _run_out_one(db, run)


async def compare_runs(
    db: AsyncSession, run_id: uuid.UUID, baseline_id: uuid.UUID
) -> CompareResponse:
    current = await db.get(EvalRun, run_id)
    baseline = await db.get(EvalRun, baseline_id)
    if not current or not baseline:
        raise AppError("NOT_FOUND", "运行记录不存在", 404)
    if current.dataset_id != baseline.dataset_id:
        raise AppError(
            "EVAL_COMPARE_INVALID", "只能对比同一数据集下的运行", 422
        )
    current_metrics = current.metrics or {}
    baseline_metrics = baseline.metrics or {}
    metric_delta = {}
    for key, value in current_metrics.items():
        if isinstance(value, (int, float)) and isinstance(
            baseline_metrics.get(key), (int, float)
        ):
            metric_delta[key] = round(
                value - baseline_metrics[key], 4
            )

    current_items = (
        await db.execute(
            select(EvalRunItem).where(EvalRunItem.run_id == run_id)
        )
    ).scalars().all()
    baseline_items = (
        await db.execute(
            select(EvalRunItem).where(EvalRunItem.run_id == baseline_id)
        )
    ).scalars().all()
    baseline_map = {
        (str(item.case_id), item.turn_index): item.passed
        for item in baseline_items
    }
    newly_failed: list[dict] = []
    newly_passed: list[dict] = []
    for item in current_items:
        key = (str(item.case_id), item.turn_index)
        if key not in baseline_map:
            continue
        was = baseline_map[key]
        now = item.passed
        if was is True and now is not True:
            newly_failed.append(
                {
                    "case_id": str(item.case_id),
                    "case_title": item.case_title,
                    "turn_index": item.turn_index,
                    "status": item.status,
                }
            )
        elif was is not True and now is True:
            newly_passed.append(
                {
                    "case_id": str(item.case_id),
                    "case_title": item.case_title,
                    "turn_index": item.turn_index,
                    "status": item.status,
                }
            )
    return CompareResponse(
        current=await _run_out_one(db, current),
        baseline=await _run_out_one(db, baseline),
        metric_delta=metric_delta,
        case_changes={
            "newly_failed": newly_failed,
            "newly_passed": newly_passed,
        },
    )


async def export_run(
    db: AsyncSession, run_id: uuid.UUID, fmt: str
) -> str:
    run = await db.get(EvalRun, run_id)
    if not run:
        raise AppError("NOT_FOUND", "评测运行不存在", 404)
    items = (
        await db.execute(
            select(EvalRunItem)
            .where(EvalRunItem.run_id == run_id)
            .order_by(EvalRunItem.case_title, EvalRunItem.turn_index)
        )
    ).scalars().all()
    if fmt == "csv":
        header = [
            "case_title",
            "turn_index",
            "status",
            "expected_type",
            "passed",
            "judge_score",
            "refused",
            "retrieval_hit",
            "retrieval_recall",
            "retrieval_rank",
            "citation_hit",
            "citation_precision",
            "latency_ms",
            "question",
            "retrieval_query",
            "answer",
            "judge_reason",
            "invalid_reason",
            "error",
        ]
        lines = [",".join(header)]
        for item in items:
            row = [
                item.case_title,
                item.turn_index,
                item.status,
                item.expected_type,
                item.passed,
                item.judge_score,
                item.refused,
                item.retrieval_hit,
                item.retrieval_recall,
                item.retrieval_rank,
                item.citation_hit,
                item.citation_precision,
                item.latency_ms,
                item.question,
                item.retrieval_query,
                item.answer,
                item.judge_reason,
                item.invalid_reason,
                item.error,
            ]
            lines.append(
                ",".join(
                    '"' + str("" if cell is None else cell).replace(
                        '"', '""'
                    ) + '"'
                    for cell in row
                )
            )
        return "\n".join(lines) + "\n"

    lines = [
        json.dumps(
            {
                "type": "eval_run_item",
                "case_title": item.case_title,
                "turn_index": item.turn_index,
                "status": item.status,
                "expected_type": item.expected_type,
                "passed": item.passed,
                "question": item.question,
                "reference_answer": item.reference_answer,
                "retrieval_query": item.retrieval_query,
                "retrieved": item.retrieved,
                "citations": item.citations,
                "answer": item.answer,
                "judge_score": item.judge_score,
                "refused": item.refused,
                "judge_reason": item.judge_reason,
                "retrieval_hit": item.retrieval_hit,
                "retrieval_recall": item.retrieval_recall,
                "retrieval_rank": item.retrieval_rank,
                "citation_hit": item.citation_hit,
                "citation_precision": item.citation_precision,
                "invalid_reason": item.invalid_reason,
                "error": item.error,
                "latency_ms": item.latency_ms,
            },
            ensure_ascii=False,
        )
        for item in items
    ]
    return "\n".join(lines) + "\n"


async def list_permissions(db: AsyncSession) -> list[dict]:
    users = (
        await db.execute(
            select(User)
            .where(User.is_active.is_(True))
            .order_by(User.role, User.display_name)
        )
    ).scalars().all()
    return [
        {
            "id": user.id,
            "username": user.username,
            "display_name": user.display_name,
            "role": user.role,
            "can_evaluate": bool(user.can_evaluate or user.role == "leader"),
        }
        for user in users
    ]


async def set_permission(
    db: AsyncSession, user_id: uuid.UUID, enabled: bool
) -> dict:
    user = await db.get(User, user_id)
    if not user:
        raise AppError("NOT_FOUND", "用户不存在", 404)
    if user.role == "leader" and not enabled:
        raise AppError(
            "EVAL_PERMISSION_INVALID", "领导默认拥有评测权限", 422
        )
    user.can_evaluate = enabled
    await db.commit()
    return {
        "id": user.id,
        "username": user.username,
        "display_name": user.display_name,
        "role": user.role,
        "can_evaluate": enabled,
    }
