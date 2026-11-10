import asyncio
import os

from sqlalchemy import select

from app.core.security import hash_password
from app.db.session import SessionLocal
from app.models.user import User

SEED_USERS = [
    (
        "leader",
        "王领导",
        "leader",
        os.getenv("SEED_LEADER_PASSWORD", "Leader@123"),
    ),
    (
        "employee1",
        "张员工",
        "employee",
        os.getenv("SEED_EMPLOYEE_PASSWORD", "Employee@123"),
    ),
    (
        "employee2",
        "李员工",
        "employee",
        os.getenv("SEED_EMPLOYEE_PASSWORD", "Employee@123"),
    ),
]


async def main() -> None:
    async with SessionLocal() as db:
        for username, display_name, role, password in SEED_USERS:
            existing = (
                await db.execute(
                    select(User).where(User.username == username)
                )
            ).scalar_one_or_none()
            if existing:
                print(f"skip existing user: {username}")
                continue
            db.add(
                User(
                    username=username,
                    display_name=display_name,
                    role=role,
                    password_hash=hash_password(password),
                )
            )
            print(f"created user: {username} / {password} ({role})")
        await db.commit()


if __name__ == "__main__":
    asyncio.run(main())
