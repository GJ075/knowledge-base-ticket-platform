import uuid

from fastapi import Depends, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError
from app.core.security import decode_access_token
from app.db.session import get_db
from app.models.user import User


async def get_current_user(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> User:
    token = request.cookies.get("access_token")
    if not token:
        authorization = request.headers.get("Authorization", "")
        if authorization.startswith("Bearer "):
            token = authorization[7:]
    if not token:
        raise AppError("AUTH_TOKEN_INVALID", "未登录或登录已过期", 401)

    user_id = decode_access_token(token)
    if not user_id:
        raise AppError("AUTH_TOKEN_INVALID", "未登录或登录已过期", 401)

    try:
        uid = uuid.UUID(user_id)
    except ValueError:
        raise AppError("AUTH_TOKEN_INVALID", "登录信息无效", 401)

    user = (
        await db.execute(select(User).where(User.id == uid))
    ).scalar_one_or_none()
    if not user or not user.is_active:
        raise AppError("AUTH_TOKEN_INVALID", "账号不存在或已禁用", 401)
    return user


async def require_leader(user: User = Depends(get_current_user)) -> User:
    if user.role != "leader":
        raise AppError("AUTH_FORBIDDEN", "需要领导权限", 403)
    return user


async def require_evaluator(user: User = Depends(get_current_user)) -> User:
    if user.role != "leader" and not user.can_evaluate:
        raise AppError("AUTH_FORBIDDEN", "没有评测权限", 403)
    return user
