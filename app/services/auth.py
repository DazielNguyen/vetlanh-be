import secrets
from datetime import UTC, datetime, timedelta

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import create_access_token, hash_password, verify_password
from app.models.user import User

# Verification token stays valid for 24 hours
_VERIFICATION_TOKEN_TTL_HOURS = 24


def _new_verification_token() -> tuple[str, datetime]:
    """Return a fresh (token, expires_at) pair."""
    token = secrets.token_urlsafe(32)
    expires_at = datetime.now(UTC) + timedelta(hours=_VERIFICATION_TOKEN_TTL_HOURS)
    return token, expires_at


async def register_user(db: AsyncSession, email: str, password: str) -> tuple[User, str]:
    """Create a new unverified user and return (user, verification_token).

    The caller is responsible for sending the verification email — typically
    via FastAPI BackgroundTasks so the HTTP response is not delayed.
    """
    result = await db.execute(select(User).where(User.email == email))
    if result.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Email already registered")

    token, expires_at = _new_verification_token()
    user = User(
        email=email,
        hashed_password=hash_password(password),
        is_verified=False,
        verification_token=token,
        verification_token_expires_at=expires_at,
    )
    db.add(user)
    # Commit immediately so the new user is visible to the very next request.
    # Without this, FastAPI's get_db commits AFTER the response is sent (after
    # BackgroundTasks), meaning a login request arriving immediately would query
    # an empty DB and get a spurious 401.
    # expire_on_commit=False (set on AsyncSessionLocal) keeps `user` readable.
    await db.commit()
    await db.refresh(user)
    return user, token


async def login_user(db: AsyncSession, email: str, password: str) -> str:
    result = await db.execute(select(User).where(User.email == email))
    user = result.scalar_one_or_none()

    if not user or not user.hashed_password or not verify_password(password, user.hashed_password):
        # Return the same error for "wrong email" and "wrong password" —
        # different messages would let attackers enumerate valid emails.
        raise HTTPException(status_code=401, detail="Invalid credentials")

    if not user.is_verified:
        # Use 403 (not 401) so the client knows credentials are correct but
        # the account needs a specific action — show "resend verification" UI.
        raise HTTPException(
            status_code=403,
            detail="Please verify your email before logging in",
        )

    return create_access_token(subject=user.email)


async def verify_email(db: AsyncSession, token: str) -> None:
    """Mark the user as verified, clearing the one-use token."""
    result = await db.execute(
        select(User).where(User.verification_token == token)
    )
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(status_code=400, detail="Invalid verification link")

    if user.is_verified:
        # Idempotent — already verified is fine; no need to error
        return

    now = datetime.now(UTC)
    if user.verification_token_expires_at and user.verification_token_expires_at < now:
        raise HTTPException(
            status_code=400,
            detail="Verification link has expired. Please request a new one.",
        )

    user.is_verified = True
    user.verification_token = None
    user.verification_token_expires_at = None
    await db.commit()


async def resend_verification(db: AsyncSession, email: str) -> str:
    """Issue a new verification token and return it (caller sends the email).

    Returns the new token so the endpoint can fire off the email via
    BackgroundTasks without touching the DB directly.
    """
    result = await db.execute(select(User).where(User.email == email))
    user = result.scalar_one_or_none()

    if not user:
        # Do NOT reveal whether the email exists — same response either way
        # (prevents email enumeration via the resend endpoint).
        return ""

    if user.is_verified:
        raise HTTPException(status_code=400, detail="Email is already verified")

    token, expires_at = _new_verification_token()
    user.verification_token = token
    user.verification_token_expires_at = expires_at
    await db.commit()
    return token


async def login_with_username(db: AsyncSession, username: str, password: str) -> str:
    result = await db.execute(select(User).where(User.username == username))
    user = result.scalar_one_or_none()

    if not user or not user.hashed_password or not verify_password(password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Invalid credentials")

    if not user.is_active:
        raise HTTPException(status_code=403, detail="Account is deactivated")

    return create_access_token(subject=username)


async def register_with_username(db: AsyncSession, username: str, password: str) -> str:
    """Create a username-only user (no email). Returns access_token immediately.

    Unlike email registration, this path skips verification entirely — the user
    is active and verified on creation. There is no recovery path if the password
    is forgotten; the caller should prompt the user to add an email.
    """
    result = await db.execute(select(User).where(User.username == username))
    if result.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Username already taken")

    user = User(
        email=None,
        username=username,
        hashed_password=hash_password(password),
        is_verified=True,
        auth_provider="username",
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return create_access_token(subject=username)


async def change_password(db: AsyncSession, user: User, current_password: str, new_password: str) -> None:
    if user.hashed_password is None:
        raise HTTPException(status_code=400, detail="Tài khoản này không có mật khẩu. Vui lòng đăng nhập bằng phương thức khác.")

    if not verify_password(current_password, user.hashed_password):
        raise HTTPException(status_code=400, detail="Mật khẩu hiện tại không đúng.")

    if current_password == new_password:
        raise HTTPException(status_code=400, detail="Mật khẩu mới không được trùng với mật khẩu hiện tại.")

    user.hashed_password = hash_password(new_password)
    await db.commit()


async def get_user_by_email(db: AsyncSession, email: str) -> User:
    result = await db.execute(select(User).where(User.email == email))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user


async def get_user_by_username(db: AsyncSession, username: str) -> User:
    result = await db.execute(select(User).where(User.username == username, User.is_active == True))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user
