import httpx
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.user import User

_GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
_GOOGLE_USERINFO_URL = "https://www.googleapis.com/oauth2/v2/userinfo"
_GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"

_SCOPES = "openid email profile"


def build_google_auth_url(state: str = "") -> str:
    params = {
        "client_id": settings.GOOGLE_CLIENT_ID,
        "redirect_uri": settings.GOOGLE_REDIRECT_URI,
        "response_type": "code",
        "scope": _SCOPES,
        "access_type": "offline",
        "state": state,
    }
    query = "&".join(f"{k}={v}" for k, v in params.items() if v)
    return f"{_GOOGLE_AUTH_URL}?{query}"


async def _exchange_code(code: str) -> dict:
    """Exchange an authorization code for an access token."""
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            _GOOGLE_TOKEN_URL,
            data={
                "code": code,
                "client_id": settings.GOOGLE_CLIENT_ID,
                "client_secret": settings.GOOGLE_CLIENT_SECRET,
                "redirect_uri": settings.GOOGLE_REDIRECT_URI,
                "grant_type": "authorization_code",
            },
        )
    if resp.status_code != 200:
        raise HTTPException(status_code=400, detail="Failed to exchange Google auth code")
    return resp.json()


async def _get_google_user_info(access_token: str) -> dict:
    """Fetch user profile from Google userinfo endpoint."""
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            _GOOGLE_USERINFO_URL,
            headers={"Authorization": f"Bearer {access_token}"},
        )
    if resp.status_code != 200:
        raise HTTPException(status_code=400, detail="Failed to fetch Google user info")
    return resp.json()


async def google_upsert_user(db: AsyncSession, code: str) -> User:
    """Exchange OAuth code → fetch profile → find or create user.

    Email collision policy:
    - auth_provider="google" + same google_id → log in (return existing user)
    - auth_provider="email" + same email → 409 (must use password login)
    - no match → create new Google-authenticated user
    """
    token_data = await _exchange_code(code)
    profile = await _get_google_user_info(token_data["access_token"])

    google_id: str = profile["id"]
    email: str = profile["email"]

    result = await db.execute(select(User).where(User.google_id == google_id))
    user = result.scalar_one_or_none()
    if user:
        return user

    result = await db.execute(select(User).where(User.email == email))
    existing = result.scalar_one_or_none()
    if existing:
        raise HTTPException(
            status_code=409,
            detail=(
                "An account with this email already exists. "
                "Please log in with your email and password."
            ),
        )

    user = User(
        email=email,
        hashed_password=None,
        is_verified=True,
        auth_provider="google",
        google_id=google_id,
    )
    db.add(user)
    await db.flush()
    await db.refresh(user)
    return user
