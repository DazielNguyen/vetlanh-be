from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.deps import get_current_user, get_db
from app.core.upload import save_upload
from app.models.subscription import Subscription
from app.models.user import User
from app.schemas.subscription import PendingSubmitRequest, PendingSubmitResponse, PaymentNotifyResponse
from app.services.email import send_payment_notify_email

router = APIRouter(prefix="/subscriptions", tags=["subscriptions"])

# Emails to notify when a new payment bill is submitted (separate from access control)
_ADMIN_EMAILS: list[str] = [e.strip() for e in settings.ADMIN_NOTIFICATION_EMAILS.split(",") if e.strip()]


@router.post("/pending", response_model=PendingSubmitResponse, status_code=201)
async def submit_pending_subscription(
    body: PendingSubmitRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    # Guard: one pending record per user — reject if already has status='pending'
    existing = (
        await db.execute(
            select(Subscription).where(
                Subscription.user_id == current_user.id,
                Subscription.status == "pending",
            )
        )
    ).scalar_one_or_none()
    if existing is not None:
        raise HTTPException(
            status_code=409,
            detail="A pending subscription request already exists for this user",
        )

    sub = Subscription(
        user_id=current_user.id,
        status="pending",
        plan_name=body.plan_name,
        duration_months=body.duration_months,
        amount_vnd=body.amount_vnd,
        transfer_date=body.transfer_date,
        transfer_note=body.transfer_note,
    )
    db.add(sub)
    await db.flush()
    return PendingSubmitResponse(id=sub.id)


@router.post("/payment-notify", response_model=PaymentNotifyResponse, status_code=201)
async def payment_notify(
    background_tasks: BackgroundTasks,
    package_key: str = Form(...),
    amount: int = Form(..., ge=1),
    transfer_note: str | None = Form(default=None),
    bill_image: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Accept multipart/form-data payment notification with bill image.

    Creates a pending subscription record and emails admins for review.
    One pending request per user — returns 409 if one already exists.
    """
    existing = (
        await db.execute(
            select(Subscription).where(
                Subscription.user_id == current_user.id,
                Subscription.status == "pending",
            )
        )
    ).scalar_one_or_none()
    if existing is not None:
        raise HTTPException(
            status_code=409,
            detail="A pending subscription request already exists for this user",
        )

    image_url = await save_upload(bill_image, "bills")

    sub = Subscription(
        user_id=current_user.id,
        status="pending",
        plan_name=package_key,
        amount_vnd=amount,
        transfer_note=transfer_note,
        bill_image_url=image_url,
    )
    db.add(sub)
    await db.flush()

    username = current_user.username or current_user.email or str(current_user.id)

    background_tasks.add_task(
        send_payment_notify_email,
        admin_emails=_ADMIN_EMAILS,
        username=username,
        package_key=package_key,
        amount=amount,
        transfer_note=transfer_note,
        subscription_id=str(sub.id),
        bill_image_url=image_url,
    )

    return PaymentNotifyResponse(id=sub.id)
