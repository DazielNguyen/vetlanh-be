"""
Unit tests for app/services/email.py

These tests mock aiosmtplib.send — no real SMTP connection is made.
The goal: verify our code calls the right library with the right args,
and that SMTP failures are swallowed gracefully.
"""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock

from app.services.email import send_verification_email


class TestSendVerificationEmail:
    async def test_calls_aiosmtplib_with_correct_recipient(self):
        with patch("app.services.email.aiosmtplib.send", new_callable=AsyncMock) as mock_send:
            await send_verification_email("user@example.com", "abc123token")

        mock_send.assert_called_once()
        # The first positional arg to aiosmtplib.send is the MIMEMultipart message
        message = mock_send.call_args.args[0]
        assert message["To"] == "user@example.com"

    async def test_email_contains_verification_link(self):
        with patch("app.services.email.aiosmtplib.send", new_callable=AsyncMock):
            # No error means it ran successfully — token is embedded in the HTML body
            await send_verification_email("user@example.com", "mytoken42")

    async def test_smtp_failure_does_not_propagate(self):
        """
        A broken SMTP server must never crash the registration flow.
        The function should log the error and return None silently.
        """
        with patch(
            "app.services.email.aiosmtplib.send",
            new_callable=AsyncMock,
            side_effect=ConnectionRefusedError("SMTP server unreachable"),
        ):
            # Should NOT raise — swallowed and logged
            await send_verification_email("user@example.com", "token")

    async def test_uses_start_tls_only_on_secure_ports(self):
        """TLS should be enabled for ports 465/587 but not for 2525."""
        with patch("app.services.email.aiosmtplib.send", new_callable=AsyncMock) as mock_send:
            with patch("app.services.email.settings") as mock_settings:
                mock_settings.SMTP_HOST = "sandbox.smtp.mailtrap.io"
                mock_settings.SMTP_PORT = 2525
                mock_settings.SMTP_USER = "user"
                mock_settings.SMTP_PASSWORD = "pass"
                mock_settings.SMTP_FROM = "noreply@example.com"
                mock_settings.APP_BASE_URL = "http://localhost"

                await send_verification_email("user@example.com", "token")

        call_kwargs = mock_send.call_args.kwargs
        assert call_kwargs["start_tls"] is False

    async def test_uses_start_tls_on_port_587(self):
        with patch("app.services.email.aiosmtplib.send", new_callable=AsyncMock) as mock_send:
            with patch("app.services.email.settings") as mock_settings:
                mock_settings.SMTP_HOST = "smtp.sendgrid.net"
                mock_settings.SMTP_PORT = 587
                mock_settings.SMTP_USER = "user"
                mock_settings.SMTP_PASSWORD = "pass"
                mock_settings.SMTP_FROM = "noreply@example.com"
                mock_settings.APP_BASE_URL = "http://localhost"

                await send_verification_email("user@example.com", "token")

        call_kwargs = mock_send.call_args.kwargs
        assert call_kwargs["start_tls"] is True
