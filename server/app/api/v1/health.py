import httpx
from fastapi import APIRouter
from fastapi.responses import JSONResponse
from redis.asyncio import Redis
from sqlalchemy import text

from app.core.config import get_settings
from app.db.session import SessionLocal
from app.services.storage import minio_health

router = APIRouter(tags=["health"])
settings = get_settings()


@router.get("/health/live")
async def live() -> dict:
    return {"status": "ok"}


@router.get("/health/ready")
async def ready() -> JSONResponse:
    components: dict[str, str] = {}
    ok = True

    try:
        async with SessionLocal() as db:
            await db.execute(text("SELECT 1"))
            missing_tsv = (
                await db.execute(
                    text(
                        "SELECT count(*) FROM document_chunks c "
                        "JOIN documents d ON d.id = c.document_id "
                        "WHERE d.is_deleted = false AND c.content_tsv IS NULL"
                    )
                )
            ).scalar_one()
        components["database"] = "ok"
        if missing_tsv:
            components["fts"] = f"degraded: {missing_tsv} chunks missing tsv"
            if settings.hybrid_enabled:
                ok = False
        else:
            components["fts"] = "ok"
    except Exception as exc:
        components["database"] = f"error: {exc}"
        ok = False

    try:
        redis = Redis.from_url(settings.redis_url)
        await redis.ping()
        await redis.aclose()
        components["redis"] = "ok"
    except Exception as exc:
        components["redis"] = f"error: {exc}"
        ok = False

    try:
        await minio_health()
        components["minio"] = "ok"
    except Exception as exc:
        components["minio"] = f"error: {exc}"
        ok = False

    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            response = await client.get(
                f"{settings.embedding_service_url}/health"
            )
            response.raise_for_status()
        components["embedding"] = "ok"
    except Exception as exc:
        components["embedding"] = f"error: {exc}"
        ok = False

    return JSONResponse(
        status_code=200 if ok else 503,
        content={
            "status": "ok" if ok else "degraded",
            "components": components,
        },
    )
