"""
Email sending service — wraps aiosmtplib for async SMTP.

Why aiosmtplib instead of smtplib:
  smtplib is blocking; calling it directly in an async handler freezes the
  event loop for every other request while the TCP handshake completes.
  aiosmtplib does the same work without blocking.
"""

import logging
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

import aiosmtplib

from app.core.config import settings

logger = logging.getLogger(__name__)


async def send_verification_email(to_email: str, token: str) -> None:
    """Send an email with a one-click verification link.

    Called via FastAPI BackgroundTasks so it never blocks the HTTP response.
    Logs the error and returns silently on failure — the user can request a
    resend; we should not crash the registration flow over an email outage.
    """
    verify_url = f"{settings.APP_BASE_URL}/api/v1/auth/verify?token={token}"

    message = MIMEMultipart("alternative")
    message["Subject"] = "Xác minh tài khoản Vết Lành"
    message["From"] = settings.SMTP_FROM
    message["To"] = to_email

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
    message.attach(MIMEText(html_body, "html"))

    try:
        await aiosmtplib.send(
            message,
            hostname=settings.SMTP_HOST,
            port=settings.SMTP_PORT,
            username=settings.SMTP_USER,
            password=settings.SMTP_PASSWORD,
            start_tls=True,
        )
        logger.info("Verification email sent to %s", to_email)
    except Exception:
        # Log full traceback but do not propagate — email outage must not
        # prevent the user from registering (they can request a resend).
        logger.exception("Failed to send verification email to %s", to_email)
