"""Quick test: send one email to confirm SMTP config works."""
import asyncio
import sys

# Load .env before importing settings
sys.path.insert(0, "/Users/vananhduy/Documents/Repository_Git_Hub/vetlanh-be")

from app.services.email import send_verification_email
from app.core.config import settings

async def main():
    print(f"SMTP: {settings.SMTP_HOST}:{settings.SMTP_PORT}")
    print(f"User: {settings.SMTP_USER[:6]}***")
    print(f"TLS ports: 465/587 — port {settings.SMTP_PORT} uses TLS: {settings.SMTP_PORT in (465, 587)}")
    print("Sending test email...")
    await send_verification_email("test@example.com", "test-token-abc123")
    print("Done — check Mailtrap inbox!")

asyncio.run(main())
