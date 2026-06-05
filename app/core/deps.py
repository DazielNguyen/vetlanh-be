from collections.abc import AsyncGenerator

from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import AsyncSessionLocal
from app.core.security import decode_access_token
from app.services.auth import get_user_by_email, get_user_by_username


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """
    Yield a database session for the duration of a request.
    Commits on success, rolls back on any exception.
    """
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


bearer_scheme = HTTPBearer()


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
    db: AsyncSession = Depends(get_db),
):
    """Extract and validate JWT token, return the authenticated User."""
    try:
        subject = decode_access_token(credentials.credentials)
    except JWTError:
        raise HTTPException(
            status_code=401,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},  # required by RFC 7235
        )

    # Email users have their email as JWT subject; username users have their username.
    # "@" is a reliable discriminator — usernames are restricted to alnum/hyphen/underscore.
    if "@" in subject:
        return await get_user_by_email(db, subject)
    return await get_user_by_username(db, subject)
