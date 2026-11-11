from uuid import UUID

from fastapi import (
    APIRouter,
    Depends,
    File,
    Query,
    Response,
    UploadFile,
)
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import require_evaluator, require_leader
from app.db.session import get_db
from app.models.user import User
from app.schemas.eval import (
    CaseIn,
    CaseOut,
    CaseUpdate,
    CompareResponse,
    DatasetCreate,
    DatasetDetail,
    DatasetListResponse,
    DatasetSummary,
    DatasetUpdate,
    PermissionListResponse,
    PermissionOut,
    PermissionUpdate,
    RunCreate,
    RunItemListResponse,
    RunListResponse,
    RunOut,
    TurnIn,
)
from app.services import eval_service

router = APIRouter(prefix="/eval", tags=["eval"])


@router.get("/datasets", response_model=DatasetListResponse)
async def list_datasets(
    include_archived: bool = False,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_evaluator),
) -> DatasetListResponse:
    return DatasetListResponse(
        items=await eval_service.list_datasets(db, include_archived)
    )


@router.post("/datasets", response_model=DatasetSummary)
async def create_dataset(
    payload: DatasetCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_evaluator),
) -> DatasetSummary:
    return await eval_service.create_dataset(
        db, user, payload.name, payload.description
    )


@router.get("/datasets/{dataset_id}", response_model=DatasetDetail)
async def dataset_detail(
    dataset_id: UUID,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_evaluator),
) -> DatasetDetail:
    return await eval_service.dataset_detail(db, dataset_id)


@router.patch("/datasets/{dataset_id}", response_model=DatasetSummary)
async def update_dataset(
    dataset_id: UUID,
    payload: DatasetUpdate,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_evaluator),
) -> DatasetSummary:
    return await eval_service.update_dataset(
        db, dataset_id, payload.name, payload.description
    )


@router.delete("/datasets/{dataset_id}", response_model=DatasetSummary)
async def archive_dataset(
    dataset_id: UUID,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_evaluator),
) -> DatasetSummary:
    return await eval_service.archive_dataset(db, dataset_id)


@router.post("/import")
async def import_dataset(
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_evaluator),
) -> dict:
    content = (await file.read()).decode("utf-8-sig", errors="replace")
    return await eval_service.import_jsonl(db, user, content)


@router.get("/datasets/{dataset_id}/export")
async def export_dataset(
    dataset_id: UUID,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_evaluator),
) -> Response:
    content = await eval_service.export_jsonl(db, dataset_id)
    return Response(
        content=content,
        media_type="application/jsonl",
        headers={
            "Content-Disposition": (
                f'attachment; filename="eval-dataset-{dataset_id}.jsonl"'
            )
        },
    )


@router.post("/datasets/{dataset_id}/cases", response_model=CaseOut)
async def create_case(
    dataset_id: UUID,
    payload: CaseIn,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_evaluator),
) -> CaseOut:
    return await eval_service.create_case(db, dataset_id, payload)


@router.patch("/cases/{case_id}", response_model=CaseOut)
async def update_case(
    case_id: UUID,
    payload: CaseUpdate,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_evaluator),
) -> CaseOut:
    return await eval_service.update_case(db, case_id, payload)


@router.put("/cases/{case_id}", response_model=CaseOut)
async def replace_case(
    case_id: UUID,
    payload: CaseIn,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_evaluator),
) -> CaseOut:
    return await eval_service.replace_case(db, case_id, payload)


@router.delete("/cases/{case_id}", status_code=204)
async def delete_case(
    case_id: UUID,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_evaluator),
) -> None:
    await eval_service.delete_case(db, case_id)


@router.post("/cases/{case_id}/turns", response_model=CaseOut)
async def create_turn(
    case_id: UUID,
    payload: TurnIn,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_evaluator),
) -> CaseOut:
    return await eval_service.create_turn(db, case_id, payload)


@router.patch("/turns/{turn_id}", response_model=CaseOut)
async def update_turn(
    turn_id: UUID,
    payload: TurnIn,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_evaluator),
) -> CaseOut:
    return await eval_service.update_turn(db, turn_id, payload)


@router.delete("/turns/{turn_id}", response_model=CaseOut)
async def delete_turn(
    turn_id: UUID,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_evaluator),
) -> CaseOut:
    return await eval_service.delete_turn(db, turn_id)


@router.post("/datasets/{dataset_id}/runs", response_model=RunOut)
async def create_run(
    dataset_id: UUID,
    payload: RunCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_evaluator),
) -> RunOut:
    return await eval_service.create_run(
        db,
        user,
        dataset_id,
        payload.retrieval_mode,
        payload.case_ids,
        payload.retrieval_config,
    )


@router.get("/runs", response_model=RunListResponse)
async def list_runs(
    dataset_id: UUID | None = None,
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_evaluator),
) -> RunListResponse:
    return await eval_service.list_runs(db, dataset_id, limit)


@router.get("/runs/{run_id}", response_model=RunOut)
async def run_detail(
    run_id: UUID,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_evaluator),
) -> RunOut:
    return await eval_service.run_detail(db, run_id)


@router.get("/runs/{run_id}/items", response_model=RunItemListResponse)
async def list_run_items(
    run_id: UUID,
    status: str | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_evaluator),
) -> RunItemListResponse:
    return await eval_service.list_run_items(
        db, run_id, status, page, page_size
    )


@router.post("/runs/{run_id}/cancel", response_model=RunOut)
async def cancel_run(
    run_id: UUID,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_evaluator),
) -> RunOut:
    return await eval_service.cancel_run(db, run_id)


@router.get("/runs/{run_id}/compare", response_model=CompareResponse)
async def compare_run(
    run_id: UUID,
    baseline_id: UUID,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_evaluator),
) -> CompareResponse:
    return await eval_service.compare_runs(db, run_id, baseline_id)


@router.get("/runs/{run_id}/export")
async def export_run(
    run_id: UUID,
    format: str = Query("jsonl", pattern="^(jsonl|csv)$"),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_evaluator),
) -> Response:
    content = await eval_service.export_run(db, run_id, format)
    media_type = "text/csv" if format == "csv" else "application/jsonl"
    return Response(
        content=content,
        media_type=media_type,
        headers={
            "Content-Disposition": (
                f'attachment; filename="eval-run-{run_id}.{format}"'
            )
        },
    )


@router.get("/permissions", response_model=PermissionListResponse)
async def list_permissions(
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_leader),
) -> PermissionListResponse:
    rows = await eval_service.list_permissions(db)
    return PermissionListResponse(
        items=[PermissionOut(**row) for row in rows]
    )


@router.patch("/permissions/{user_id}", response_model=PermissionOut)
async def set_permission(
    user_id: UUID,
    payload: PermissionUpdate,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_leader),
) -> PermissionOut:
    row = await eval_service.set_permission(
        db, user_id, payload.can_evaluate
    )
    return PermissionOut(**row)
