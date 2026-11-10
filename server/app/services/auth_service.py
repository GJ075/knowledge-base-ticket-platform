from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import verify_password
from app.models.user import User


async def authenticate(
    db: AsyncSession, username: str, password: str
) -> User | None:
    user = (
        await db.execute(select(User).where(User.username == username))
    ).scalar_one_or_none()
    if not user or not user.is_active:
        return None
    if not verify_password(password, user.password_hash):
        return None
    return user
