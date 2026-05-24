from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import create_access_token, hash_password, verify_password
from app.models.user import User


async def register_user(db: AsyncSession, email: str, password: str) -> User:
    result = await db.execute(select(User).where(User.email == email))
    if result.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Email already registered")

    user = User(email=email, hashed_password=hash_password(password))
    db.add(user)
    # flush assigns the DB-generated id without committing the transaction;
    # the actual commit happens in get_db when the request completes cleanly.
    await db.flush()
    return user


async def login_user(db: AsyncSession, email: str, password: str) -> str:
    result = await db.execute(select(User).where(User.email == email))
    user = result.scalar_one_or_none()

    if not user or not verify_password(password, user.hashed_password):
        # Return the same error for "wrong email" and "wrong password" —
        # different messages would let attackers enumerate valid emails.
        raise HTTPException(status_code=401, detail="Invalid credentials")

    return create_access_token(subject=user.email)


async def get_user_by_email(db: AsyncSession, email: str) -> User:
    result = await db.execute(select(User).where(User.email == email))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user
