from fastapi import APIRouter, BackgroundTasks, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_db
from app.schemas.auth import MessageResponse, ResendRequest, Token, UserLogin, UserRegister, UserResponse
from app.services.auth import login_user, register_user, resend_verification, verify_email
from app.services.email import send_verification_email

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
