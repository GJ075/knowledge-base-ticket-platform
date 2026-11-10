import logging

from fastapi import Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import DBAPIError

logger = logging.getLogger("app")

_FIELD_LABELS = {
    "title": "标题",
    "description": "描述",
    "filename": "文件名",
}


class AppError(Exception):
    def __init__(self, code: str, message: str, status_code: int = 400):
        self.code = code
        self.message = message
        self.status_code = status_code


def error_payload(code: str, message: str, details: dict | None = None) -> dict:
    return {"error": {"code": code, "message": message, "details": details or {}}}


async def app_error_handler(request: Request, exc: AppError) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content=error_payload(exc.code, exc.message),
    )


async def validation_error_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    errors = exc.errors()
    message = "请求参数校验失败"
    if errors:
        first = errors[0]
        loc = [
            str(part)
            for part in first.get("loc", [])
            if part not in ("body", "query", "path")
        ]
        field = _FIELD_LABELS.get(
            loc[-1] if loc else "", loc[-1] if loc else "参数"
        )
        kind = first.get("type")
        if kind == "string_too_long":
            limit = first.get("ctx", {}).get("max_length")
            message = f"{field}不能超过 {limit} 个字符"
        elif kind == "string_too_short":
            message = f"{field}不能为空"
    return JSONResponse(
        status_code=422,
        content=error_payload(
            "VALIDATION_ERROR",
            message,
            {"errors": jsonable_encoder(errors)},
        ),
    )


async def db_error_handler(
    request: Request, exc: DBAPIError
) -> JSONResponse:
    logger.error("database operation failed", exc_info=exc)
    return JSONResponse(
        status_code=500,
        content=error_payload(
            "DATABASE_ERROR",
            "数据库操作失败，请稍后重试",
        ),
    )
