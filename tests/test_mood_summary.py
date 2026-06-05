"""
Tests for mood summary endpoint — GET /api/v1/users/me/mood-summary.

Covers:
  1. No auth → 401
  2. No entries → empty list
  3. Entries within last N days are returned (sparse — only days with entries)
  4. Entries outside the window are excluded
  5. Each item has date (YYYY-MM-DD) and sentiment_score (int 1–5)
  6. Default days=7; explicit days param works
  7. days out of range → 422
"""

import unittest.mock as mock
from datetime import datetime, timedelta, timezone

import pytest
from httpx import AsyncClient

TEST_EMAIL_DOMAIN = "test.vetlanh"
SUMMARY_URL = "/api/v1/users/me/mood-summary"
ENTRIES_URL = "/api/v1/mood/entries"

_VN_TZ = timezone(timedelta(hours=7))


async def _register_and_login(client: AsyncClient, email: str) -> str:
    captured = []

    async def capture(*args, **kwargs):
        captured.append(args)

    with mock.patch("app.api.v1.endpoints.auth.send_verification_email", side_effect=capture):
        await client.post("/api/v1/auth/register", json={"email": email, "password": "securepass1"})

    token = captured[0][1]
    await client.get(f"/api/v1/auth/verify?token={token}")

    resp = await client.post("/api/v1/auth/login", json={"email": email, "password": "securepass1"})
    assert resp.status_code == 200
    return resp.json()["access_token"]


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


async def _post_mood(client: AsyncClient, token: str, date_str: str, mood: int = 3):
    payload = {"date": date_str, "mood": mood, "energy": "medium", "factors": [], "note": None}
    resp = await client.post(ENTRIES_URL, json=payload, headers=_auth(token))
    assert resp.status_code in (200, 201), f"Failed to create mood entry: {resp.text}"


@pytest.mark.asyncio
async def test_summary_requires_auth(client: AsyncClient):
    """1. No auth → 401."""
    resp = await client.get(SUMMARY_URL)
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_summary_empty_when_no_entries(client: AsyncClient):
    """2. No entries → empty list."""
    token = await _register_and_login(client, f"summary_empty@{TEST_EMAIL_DOMAIN}")
    resp = await client.get(SUMMARY_URL, headers=_auth(token))
    assert resp.status_code == 200
    assert resp.json() == []


@pytest.mark.asyncio
async def test_summary_returns_entries_in_window(client: AsyncClient):
    """3. Entry within last 7 days is included; has correct fields."""
    token = await _register_and_login(client, f"summary_window@{TEST_EMAIL_DOMAIN}")
    today = datetime.now(tz=_VN_TZ).date()
    await _post_mood(client, token, str(today), mood=4)

    resp = await client.get(SUMMARY_URL, params={"days": 7}, headers=_auth(token))
    assert resp.status_code == 200
    items = resp.json()
    assert len(items) == 1
    assert items[0]["date"] == str(today)
    assert items[0]["sentiment_score"] == 4


@pytest.mark.asyncio
async def test_summary_excludes_entries_outside_window(client: AsyncClient):
    """4. Entry older than `days` window is excluded."""
    token = await _register_and_login(client, f"summary_outside@{TEST_EMAIL_DOMAIN}")
    today = datetime.now(tz=_VN_TZ).date()
    old_date = today - timedelta(days=10)
    await _post_mood(client, token, str(old_date), mood=2)

    resp = await client.get(SUMMARY_URL, params={"days": 7}, headers=_auth(token))
    assert resp.status_code == 200
    assert resp.json() == []


@pytest.mark.asyncio
async def test_summary_explicit_days_param(client: AsyncClient):
    """6. Explicit days=30 includes entry from 10 days ago."""
    token = await _register_and_login(client, f"summary_days30@{TEST_EMAIL_DOMAIN}")
    today = datetime.now(tz=_VN_TZ).date()
    old_date = today - timedelta(days=10)
    await _post_mood(client, token, str(old_date), mood=3)

    resp = await client.get(SUMMARY_URL, params={"days": 30}, headers=_auth(token))
    assert resp.status_code == 200
    items = resp.json()
    assert len(items) == 1
    assert items[0]["date"] == str(old_date)


@pytest.mark.asyncio
async def test_summary_days_out_of_range(client: AsyncClient):
    """7. days=0 and days=91 → 422."""
    token = await _register_and_login(client, f"summary_422@{TEST_EMAIL_DOMAIN}")
    resp_low = await client.get(SUMMARY_URL, params={"days": 0}, headers=_auth(token))
    assert resp_low.status_code == 422

    resp_high = await client.get(SUMMARY_URL, params={"days": 91}, headers=_auth(token))
    assert resp_high.status_code == 422
