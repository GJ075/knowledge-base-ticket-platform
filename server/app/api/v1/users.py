from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import require_leader
from app.db.session import get_db
from app.models.user import User
from app.schemas.user import UserBrief

router = APIRouter(prefix="/users", tags=["users"])


@router.get("")
async def list_users(
    role: str | None = None,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_leader),
) -> dict:
    query = (
        select(User)
        .where(User.is_active.is_(True))
        .order_by(User.display_name)
    )
    if role:
        query = query.where(User.role == role)
    users = (await db.execute(query)).scalars().all()
    return {
        "items": [
            UserBrief.model_validate(user).model_dump(mode="json")
            for user in users
        ]
    }
