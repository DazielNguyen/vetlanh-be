from urllib.parse import quote

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from fastapi.responses import RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.deps import get_db
from app.core.security import create_access_token
from app.schemas.auth import MessageResponse, ResendRequest, Token, UserLogin, UserRegister, UsernameLogin, UsernameRegister, UserResponse
from app.services.auth import login_user, login_with_username, register_user, register_with_username, resend_verification, verify_email
from app.services.email import send_verification_email
from app.services.oauth import build_google_auth_url, google_upsert_user

router = APIRouter()


@router.post("/auth/register", response_model=UserResponse, status_code=201)
async def register(
    body: UserRegister,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
):
    user, token = await register_user(db, body.email, body.password)

    # Fire-and-forget — email is sent after the HTTP response is returned.
    # If the SMTP server is unreachable, the error is logged but the user is
    # still registered; they can use /auth/resend-verification.
    background_tasks.add_task(send_verification_email, user.email, token)

    return user


@router.post("/auth/register-username", response_model=Token, status_code=201)
async def register_username(body: UsernameRegister, db: AsyncSession = Depends(get_db)):
    token = await register_with_username(db, body.username, body.password)
    return Token(access_token=token)


@router.post("/auth/login-username", response_model=Token)
async def login_username(body: UsernameLogin, db: AsyncSession = Depends(get_db)):
    token = await login_with_username(db, body.username, body.password)
    return Token(access_token=token)


@router.post("/auth/login", response_model=Token)
async def login(body: UserLogin, db: AsyncSession = Depends(get_db)):
    token = await login_user(db, body.email, body.password)
    return Token(access_token=token)


@router.get("/auth/verify", response_model=MessageResponse)
async def verify(
    token: str = Query(..., description="Verification token from email link"),
    db: AsyncSession = Depends(get_db),
):
    await verify_email(db, token)
    return MessageResponse(message="Email verified successfully. You can now log in.")


@router.get("/auth/google")
async def google_auth():
    """Return the Google OAuth authorization URL for the frontend to redirect to."""
    url = build_google_auth_url()
    return {"authorization_url": url}


@router.get("/auth/google/callback")
async def google_callback(
    code: str = Query(..., description="Authorization code returned by Google"),
    db: AsyncSession = Depends(get_db),
):
    """Exchange the Google authorization code for a JWT, then redirect to the frontend."""
    try:
        user = await google_upsert_user(db, code)
        await db.commit()
        token = create_access_token(subject=user.email)
        return RedirectResponse(f"{settings.FRONTEND_URL}/auth/google/callback?token={token}")
    except HTTPException as exc:
        error_msg = quote(str(exc.detail))
        return RedirectResponse(f"{settings.FRONTEND_URL}/login?error={error_msg}")


@router.post("/auth/resend-verification", response_model=MessageResponse)
async def resend(
    body: ResendRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
):
    token = await resend_verification(db, body.email)
    if token:
        background_tasks.add_task(send_verification_email, body.email, token)

    # Always return the same message — prevents email enumeration
    return MessageResponse(
        message="If that email is registered and unverified, a new link has been sent."
    )
