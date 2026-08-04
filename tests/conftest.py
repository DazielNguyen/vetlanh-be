"""
Shared fixtures for all test modules.

Why each fixture exists:
  client       — sends HTTP requests to the app in-memory (no real server needed)
  mock_email   — prevents real SMTP calls during tests (autouse: applies everywhere)
  clean_db     — deletes test rows before each test to prevent state leaking between tests
"""

import os

# Set required env vars before any app module is imported so Settings() doesn't fail.
# These are placeholders — no real API calls are made in unit tests (everything is mocked).
os.environ.setdefault("OPENAI_API_KEY", "test-openai-key")
# Valid Fernet key for tests — does not need to match production key
os.environ.setdefault("JOURNAL_ENCRYPTION_KEY", "_RcBQAY99s_WZg4RGlmiNqOCfKYXX-g0st5bsZLSl38=")

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from unittest.mock import AsyncMock, patch

from app.core.database import AsyncSessionLocal
from app.main import app

# All test users use this domain so the cleanup fixture can target them precisely.
TEST_EMAIL_DOMAIN = "test.vetlanh"


@pytest.fixture
async def client() -> AsyncClient:
    """In-process AsyncClient — talks to the app without a real TCP server."""
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as c:
        yield c


@pytest.fixture(autouse=True)
def mock_email():
    """
    Patch send_verification_email in the auth endpoint module for every test.

    autouse=True means this runs automatically — no need to request it explicitly.
    Using AsyncMock because BackgroundTasks awaits async functions.
    """
    with patch(
        "app.api.v1.endpoints.auth.send_verification_email",
        new_callable=AsyncMock,
    ) as mock:
        yield mock


@pytest.fixture(autouse=True)
async def clean_db():
    """
    Delete all test users before each test.

    Running BEFORE (not after) ensures a clean state even if a previous test
    crashed before its own cleanup ran.
    """
    async with AsyncSessionLocal() as db:
        # Community moderation keeps evidence with RESTRICT foreign keys. Remove
        # only rows linked to test-domain accounts, in dependency order.
        test_users = (
            f"SELECT id FROM users WHERE email LIKE '%@{TEST_EMAIL_DOMAIN}'"
        )
        test_matches = (
            "SELECT id FROM community_matches "
            f"WHERE user1_id IN ({test_users}) OR user2_id IN ({test_users})"
        )
        test_reports = (
            "SELECT id FROM community_reports "
            f"WHERE reporter_id IN ({test_users}) OR reported_id IN ({test_users})"
        )
        await db.execute(
            text(
                "DELETE FROM community_moderation_actions "
                f"WHERE report_id IN ({test_reports})"
            )
        )
        await db.execute(
            text(
                "DELETE FROM community_reports "
                f"WHERE reporter_id IN ({test_users}) OR reported_id IN ({test_users})"
            )
        )
        await db.execute(
            text(
                "DELETE FROM community_blocks "
                f"WHERE blocker_id IN ({test_users}) OR blocked_id IN ({test_users})"
            )
        )
        await db.execute(
            text(
                "DELETE FROM community_messages "
                f"WHERE match_id IN ({test_matches})"
            )
        )
        await db.execute(
            text(
                "DELETE FROM community_participations "
                f"WHERE user_id IN ({test_users})"
            )
        )
        await db.execute(text(f"DELETE FROM community_matches WHERE id IN ({test_matches})"))
        await db.execute(
            text(f"DELETE FROM users WHERE email LIKE '%@{TEST_EMAIL_DOMAIN}'")
        )
        # events has no FK to users (unauthenticated ingestion) and no test-domain
        # scoping is possible — clear it entirely for isolation between test runs.
        await db.execute(text("DELETE FROM events"))
        await db.commit()
    yield
