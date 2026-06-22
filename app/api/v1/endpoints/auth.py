from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_user, get_db
from app.core.rate_limit import limiter
from app.models.user import User
from app.schemas.auth import ChangePasswordRequest, MessageResponse, ResendRequest, Token, UserLogin, UserRegister, UsernameLogin, UsernameRegister, UserResponse
from app.services.auth import change_password, login_user, login_with_username, register_user, register_with_username, resend_verification, verify_email
from app.services.email import send_verification_email
from app.services.settings import confirm_email_change

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


@router.post("/auth/change-password", response_model=MessageResponse)
@limiter.limit("5/minute")
async def change_password_endpoint(
    request: Request,
    body: ChangePasswordRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await change_password(db, current_user, body.current_password, body.new_password)
    return MessageResponse(message="Mật khẩu đã được cập nhật thành công.")


@router.get("/auth/verify-email-change", response_model=MessageResponse)
async def verify_email_change(
    token: str = Query(..., description="Email change token from the confirmation link"),
    db: AsyncSession = Depends(get_db),
):
    await confirm_email_change(db, token)
    return MessageResponse(message="Email đã được cập nhật thành công.")
