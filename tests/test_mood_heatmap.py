"""
Tests for US-015 — Mood Heatmap Calendar.

Covers:
  API integration tests (real DB via AsyncClient):
    1. GET /heatmap without token → 401
    2. Month with no entries → 200, days=[]
    3. Month with 2 entries → 200, days has 2 items in ascending date order
    4. Each day item has date (YYYY-MM-DD string) and mood_score (int 1–5)
    5. ?year=2026&month=13 → 422
    6. ?year=1999&month=6 → 422
    7. Response envelope contains correct year and month values
    8. Entries from a different month are NOT included in the response
"""

import unittest.mock as mock

import pytest
from httpx import AsyncClient

TEST_EMAIL_DOMAIN = "test.vetlanh"
HEATMAP_URL = "/api/v1/mood/heatmap"
ENTRIES_URL = "/api/v1/mood/entries"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


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


def _auth_header(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


async def _post_mood_entry(client: AsyncClient, token: str, date_str: str, mood: int = 3):
    payload = {"date": date_str, "mood": mood, "energy": "medium", "factors": [], "note": None}
    resp = await client.post(ENTRIES_URL, json=payload, headers=_auth_header(token))
    assert resp.status_code in (200, 201), f"Failed to create mood entry: {resp.text}"
    return resp


# ---------------------------------------------------------------------------
# API integration tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_heatmap_requires_auth(client: AsyncClient):
    """1. GET /heatmap without token → 401."""
    resp = await client.get(HEATMAP_URL, params={"year": 2026, "month": 5})
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_heatmap_empty_month(client: AsyncClient):
    """2. Month with no entries → 200, days=[]."""
    token = await _register_and_login(client, f"heatmap_empty@{TEST_EMAIL_DOMAIN}")
    resp = await client.get(HEATMAP_URL, params={"year": 2026, "month": 3}, headers=_auth_header(token))
    assert resp.status_code == 200
    body = resp.json()
    assert body["days"] == []


@pytest.mark.asyncio
async def test_heatmap_two_entries_ascending_order(client: AsyncClient):
    """3. Month with 2 entries → 200, days has 2 items in ascending date order."""
    token = await _register_and_login(client, f"heatmap_two@{TEST_EMAIL_DOMAIN}")
    await _post_mood_entry(client, token, "2026-05-15", mood=4)
    await _post_mood_entry(client, token, "2026-05-03", mood=2)

    resp = await client.get(HEATMAP_URL, params={"year": 2026, "month": 5}, headers=_auth_header(token))
    assert resp.status_code == 200
    days = resp.json()["days"]
    assert len(days) == 2
    # Ascending date order
    assert days[0]["date"] < days[1]["date"]
    dates = [d["date"] for d in days]
    assert "2026-05-03" in dates
    assert "2026-05-15" in dates


@pytest.mark.asyncio
async def test_heatmap_day_item_shape(client: AsyncClient):
    """4. Each day item has date (YYYY-MM-DD string) and mood_score (int 1–5)."""
    token = await _register_and_login(client, f"heatmap_shape@{TEST_EMAIL_DOMAIN}")
    await _post_mood_entry(client, token, "2026-05-10", mood=5)

    resp = await client.get(HEATMAP_URL, params={"year": 2026, "month": 5}, headers=_auth_header(token))
    assert resp.status_code == 200
    days = resp.json()["days"]
    assert len(days) == 1
    day = days[0]

    # date is a YYYY-MM-DD string
    assert isinstance(day["date"], str)
    assert day["date"] == "2026-05-10"

    # mood_score is an int in 1–5
    assert isinstance(day["mood_score"], int)
    assert 1 <= day["mood_score"] <= 5
    assert day["mood_score"] == 5


@pytest.mark.asyncio
async def test_heatmap_invalid_month_13(client: AsyncClient):
    """5. ?year=2026&month=13 → 422."""
    token = await _register_and_login(client, f"heatmap_val1@{TEST_EMAIL_DOMAIN}")
    resp = await client.get(HEATMAP_URL, params={"year": 2026, "month": 13}, headers=_auth_header(token))
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_heatmap_invalid_year_1999(client: AsyncClient):
    """6. ?year=1999&month=6 → 422."""
    token = await _register_and_login(client, f"heatmap_val2@{TEST_EMAIL_DOMAIN}")
    resp = await client.get(HEATMAP_URL, params={"year": 1999, "month": 6}, headers=_auth_header(token))
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_heatmap_response_envelope(client: AsyncClient):
    """7. Response envelope contains correct year and month values."""
    token = await _register_and_login(client, f"heatmap_envelope@{TEST_EMAIL_DOMAIN}")
    resp = await client.get(HEATMAP_URL, params={"year": 2025, "month": 8}, headers=_auth_header(token))
    assert resp.status_code == 200
    body = resp.json()
    assert body["year"] == 2025
    assert body["month"] == 8
    assert "days" in body


@pytest.mark.asyncio
async def test_heatmap_excludes_different_month_entries(client: AsyncClient):
    """8. Entries from a different month are NOT included in the response."""
    token = await _register_and_login(client, f"heatmap_isolate@{TEST_EMAIL_DOMAIN}")

    # Entry in May
    await _post_mood_entry(client, token, "2026-05-20", mood=3)
    # Entry in April (different month)
    await _post_mood_entry(client, token, "2026-04-10", mood=5)

    # Request heatmap for May only
    resp = await client.get(HEATMAP_URL, params={"year": 2026, "month": 5}, headers=_auth_header(token))
    assert resp.status_code == 200
    days = resp.json()["days"]
    dates = [d["date"] for d in days]

    assert "2026-05-20" in dates
    assert "2026-04-10" not in dates
    assert len(days) == 1
