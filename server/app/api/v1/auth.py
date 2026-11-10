from fastapi import APIRouter, Depends, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.deps import get_current_user
from app.core.errors import AppError
from app.core.security import create_access_token
from app.db.session import get_db
from app.models.user import User
from app.schemas.auth import LoginRequest, LoginResponse, UserOut
from app.services.auth_service import authenticate

router = APIRouter(prefix="/auth", tags=["auth"])
settings = get_settings()


@router.post("/login", response_model=LoginResponse)
async def login(
    payload: LoginRequest,
    response: Response,
    db: AsyncSession = Depends(get_db),
) -> LoginResponse:
    user = await authenticate(db, payload.username, payload.password)
    if not user:
        raise AppError(
            "AUTH_INVALID_CREDENTIALS", "用户名或密码错误", 401
        )
    token = create_access_token(str(user.id))
    response.set_cookie(
        key="access_token",
        value=token,
        httponly=True,
        samesite="lax",
        secure=settings.cookie_secure,
        max_age=settings.jwt_expire_minutes * 60,
        path="/",
    )
    return LoginResponse(user=UserOut.model_validate(user))


@router.post("/logout", status_code=204)
async def logout(response: Response) -> None:
    response.delete_cookie("access_token", path="/")


@router.get("/me", response_model=UserOut)
async def me(user: User = Depends(get_current_user)) -> UserOut:
    return UserOut.model_validate(user)
