import logging
from collections.abc import AsyncGenerator

from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import AsyncSessionLocal
from app.core.security import decode_access_token
from app.services.auth import get_user_by_email, get_user_by_username

logger = logging.getLogger(__name__)

# Parse ADMIN_USERS once at startup via pydantic-settings (reads .env correctly).
# Empty set → no admin access. A warning fires so misconfigured deploys are
# immediately visible in logs rather than silently blocking all admin access.
_ADMIN_USERS: frozenset[str] = frozenset(
    u.strip() for u in settings.ADMIN_USERS.split(",") if u.strip()
)
if not _ADMIN_USERS:
    logger.warning("ADMIN_USERS is empty — no admin access is possible")


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


async def require_admin(
    current_user=Depends(get_current_user),
):
    """Guard: valid JWT first (401 if missing/invalid), then admin whitelist (403 if not admin).

    Uses the same "@" discriminator as get_current_user so email users are matched
    against their email address and username users against their username, preventing
    namespace confusion between the two registration types.
    """
    # Check both username and email so admins can be listed by either.
    # A user registered via email has a valid username too — requiring only one form
    # would force the operator to know which field to use.
    identities = {v for v in (current_user.username, current_user.email) if v}
    if not identities & _ADMIN_USERS:
        raise HTTPException(status_code=403, detail="Admin access required")
    return current_user
