"""
Email sending service — uses the Resend API for transactional email.

Why asyncio.to_thread:
  resend.Emails.send() is a synchronous HTTP call. Wrapping it in
  asyncio.to_thread() offloads it to a worker thread so the event loop
  is never blocked while waiting for the Resend API response.
"""

import asyncio
import logging
from urllib.parse import quote

import resend

from app.core.config import settings

logger = logging.getLogger(__name__)

# Set once at import time so the key is never mutated inside a thread.
resend.api_key = settings.RESEND_API_KEY


async def send_payment_notify_email(
    admin_emails: list[str],
    username: str,
    package_key: str,
    amount: int,
    transfer_note: str | None,
    subscription_id: str,
    bill_image_url: str,
) -> None:
    """Notify admins that a user submitted a payment and is awaiting approval.

    Fire-and-forget — logged on failure, never raises.
    """
    if not admin_emails:
        logger.warning("No admin emails configured — skipping payment notify email")
        return

    admin_url = f"{settings.APP_BASE_URL}/admin/subscriptions"
    note_line = f"<p><strong>Ghi chú:</strong> {transfer_note}</p>" if transfer_note else ""

    html_body = f"""
    <html>
      <body style="font-family: sans-serif; color: #333; max-width: 520px; margin: 0 auto;">
        <h2 style="color: #4A7C59;">Yêu cầu thanh toán mới</h2>
        <p>Người dùng <strong>{username}</strong> đã gửi xác nhận thanh toán:</p>
        <ul>
          <li><strong>Gói:</strong> {package_key}</li>
          <li><strong>Số tiền:</strong> {amount:,}đ</li>
          {note_line}
        </ul>
        <p><a href="{bill_image_url}" style="color:#4A7C59;">Xem ảnh bill</a></p>
        <a href="{admin_url}"
           style="display:inline-block; padding:12px 24px; background:#4A7C59;
                  color:#fff; text-decoration:none; border-radius:6px; margin:16px 0;">
          Duyệt ngay
        </a>
        <p style="color:#999; font-size:13px;">ID: {subscription_id}</p>
      </body>
    </html>
    """

    params: resend.Emails.SendParams = {
        "from": settings.EMAIL_FROM,
        "to": admin_emails,
        "subject": f"[Vết Lành] Thanh toán mới từ {username}",
        "html": html_body,
    }

    try:
        await asyncio.to_thread(resend.Emails.send, params)
        logger.info("Payment notify email sent to admins for subscription %s", subscription_id)
    except Exception:
        logger.exception("Failed to send payment notify email for subscription %s", subscription_id)


async def send_verification_email(to_email: str, token: str) -> None:
    """Send an email with a one-click verification link.

    Called via FastAPI BackgroundTasks so it never blocks the HTTP response.
    Logs the error and returns silently on failure — the user can request a
    resend; we should not crash the registration flow over an email outage.
    """
    verify_url = f"{settings.FRONTEND_BASE_URL}/verify?token={quote(token, safe='')}"

    html_body = f"""
    <html>
      <body style="font-family: sans-serif; color: #333; max-width: 480px; margin: 0 auto;">
        <h2 style="color: #4A7C59;">Chào mừng đến với Vết Lành 🌿</h2>
        <p>Cảm ơn bạn đã đăng ký. Nhấn vào nút bên dưới để xác minh email của bạn:</p>
        <a href="{verify_url}"
           style="display:inline-block; padding:12px 24px; background:#4A7C59;
                  color:#fff; text-decoration:none; border-radius:6px; margin:16px 0;">
          Xác minh email
        </a>
        <p style="color: #999; font-size: 13px;">
          Liên kết có hiệu lực trong 24 giờ.<br>
          Nếu bạn không đăng ký tài khoản này, hãy bỏ qua email này.
        </p>
      </body>
    </html>
    """

    params: resend.Emails.SendParams = {
        "from": settings.EMAIL_FROM,
        "to": [to_email],
        "subject": "Xác minh tài khoản Vết Lành",
        "html": html_body,
    }

    try:
        await asyncio.to_thread(resend.Emails.send, params)
        logger.info("Verification email sent to %s", to_email)
    except Exception:
        # Log full traceback but do not propagate — email outage must not
        # prevent the user from registering (they can request a resend).
        logger.exception("Failed to send verification email to %s", to_email)
