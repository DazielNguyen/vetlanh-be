import secrets
from datetime import UTC, datetime, timedelta

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import verify_password
from app.models.user import User

_EMAIL_CHANGE_TOKEN_TTL_HOURS = 1


async def request_email_change(
    db: AsyncSession, user: User, new_email: str, current_password: str
) -> str:
    """Validate the request, store the pending change, and return the confirmation token."""
    if user.hashed_password is None:
        raise HTTPException(status_code=400, detail="Tài khoản này không có mật khẩu. Vui lòng đăng nhập bằng phương thức khác.")

    if not verify_password(current_password, user.hashed_password):
        raise HTTPException(status_code=400, detail="Mật khẩu không đúng.")

    if user.email and new_email.lower() == user.email.lower():
        raise HTTPException(status_code=400, detail="Email mới không được trùng với email hiện tại.")

    existing = (await db.execute(select(User).where(User.email == new_email))).scalar_one_or_none()
    if existing:
        raise HTTPException(status_code=400, detail="Email này đã được sử dụng bởi tài khoản khác.")

    token = secrets.token_urlsafe(32)
    user.pending_email = new_email
    user.email_change_token = token
    user.email_change_token_expires_at = datetime.now(UTC) + timedelta(hours=_EMAIL_CHANGE_TOKEN_TTL_HOURS)
    await db.commit()
    return token


async def confirm_email_change(db: AsyncSession, token: str) -> None:
    """Apply the pending email change identified by token."""
    user = (
        await db.execute(select(User).where(User.email_change_token == token))
    ).scalar_one_or_none()

    if not user or not user.pending_email:
        raise HTTPException(status_code=400, detail="Liên kết xác nhận không hợp lệ hoặc đã hết hạn.")

    now = datetime.now(UTC)
    if user.email_change_token_expires_at and user.email_change_token_expires_at < now:
        raise HTTPException(status_code=400, detail="Liên kết xác nhận không hợp lệ hoặc đã hết hạn.")

    existing = (
        await db.execute(select(User).where(User.email == user.pending_email))
    ).scalar_one_or_none()
    if existing:
        raise HTTPException(status_code=409, detail="Email này đã được sử dụng bởi tài khoản khác.")

    user.email = user.pending_email
    user.pending_email = None
    user.email_change_token = None
    user.email_change_token_expires_at = None
    await db.commit()
