import logging
import time
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.exc import DBAPIError

from app.api.v1.health import router as health_router
from app.api.v1.router import api_router
from app.core.config import get_settings
from app.core.errors import (
    AppError,
    app_error_handler,
    db_error_handler,
    validation_error_handler,
)
from app.core.logging import configure_logging
from app.services.storage import ensure_buckets

settings = get_settings()
logger = logging.getLogger("app")


@asynccontextmanager
async def lifespan(app: FastAPI):
    configure_logging()
    if not settings.deepseek_api_key.strip():
        logger.warning(
            "DEEPSEEK_API_KEY 未配置，RAG 将使用本地模拟回答"
        )
    try:
        await ensure_buckets()
    except Exception as exc:
        logger.warning("ensure buckets failed: %s", exc)
    yield


app = FastAPI(
    title="企业知识库工单系统",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_exception_handler(AppError, app_error_handler)
app.add_exception_handler(RequestValidationError, validation_error_handler)
app.add_exception_handler(DBAPIError, db_error_handler)


@app.middleware("http")
async def request_logging(request: Request, call_next):
    request_id = request.headers.get("X-Request-ID", uuid.uuid4().hex)
    start = time.perf_counter()
    response = await call_next(request)
    latency_ms = round((time.perf_counter() - start) * 1000, 2)
    logger.info(
        "request",
        extra={
            "request_id": request_id,
            "method": request.method,
            "path": request.url.path,
            "status": response.status_code,
            "latency_ms": latency_ms,
        },
    )
    response.headers["X-Request-ID"] = request_id
    return response


app.include_router(health_router)
app.include_router(api_router, prefix="/api/v1")
