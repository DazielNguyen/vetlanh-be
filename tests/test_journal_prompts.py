"""
Tests for US-029 — Journal Prompts.

Covers:
  Pure function unit tests (no DB):
    get_daily_prompt:
      - Same user_id + same date → same prompt (deterministic)
      - Same date, different user_id → different prompt (most likely)
      - Returns a dict with id, topic, text fields
      - None today param falls back to date.today()
      - Returns a prompt from within the known prompt list

    get_next_prompt:
      - Returns prompt after the given current_id
      - Wraps around: last prompt → first prompt
      - Invalid current_id → wraps gracefully (index -1 + 1 == 0)

    list_by_topic:
      - None → returns all 32 prompts
      - "work_stress" → returns only work_stress prompts (8 items)
      - "relationships" → returns only relationship prompts (8 items)
      - "self_compassion" → returns only self_compassion prompts (8 items)
      - "gratitude" → returns only gratitude prompts (8 items)
      - Unknown topic → returns empty list

  API integration tests (real DB via AsyncClient):
    - GET /api/v1/journal/prompts/daily → 401 without token
    - GET /api/v1/journal/prompts/daily → 200, returns prompt + topics list
    - GET /api/v1/journal/prompts/daily → same prompt on two calls same day (deterministic)
    - GET /api/v1/journal/prompts/next?current_id=1 → 200, returns next prompt
    - GET /api/v1/journal/prompts/next?current_id=32 → 200, wraps to first prompt
    - GET /api/v1/journal/prompts → 200, returns all 32 prompts
    - GET /api/v1/journal/prompts?topic=gratitude → 200, all returned items have topic=gratitude
    - GET /api/v1/journal/prompts?topic=unknown → 200, returns empty list
    - Auth required on all endpoints
"""

from datetime import date
from unittest.mock import patch

import pytest
from httpx import AsyncClient

from app.services.journal_prompts import _PROMPTS, get_daily_prompt, get_next_prompt, list_by_topic

TEST_EMAIL_DOMAIN = "test.vetlanh"

_TOTAL_PROMPTS = 32


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _register_and_login(client: AsyncClient, email: str) -> str:
    """Register → verify → login → return Bearer token."""
    import unittest.mock as mock

    captured = []

    async def capture(*args, **kwargs):
        captured.append(args)

    with mock.patch("app.api.v1.endpoints.auth.send_verification_email", side_effect=capture):
        await client.post("/api/v1/auth/register", json={"email": email, "password": "securepass1"})

    token = captured[0][1]
    await client.get(f"/api/v1/auth/verify?token={token}")

    resp = await client.post("/api/v1/auth/login", json={"email": email, "password": "securepass1"})
    assert resp.status_code == 200, f"Login failed: {resp.text}"
    return resp.json()["access_token"]


def _auth_header(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


# ---------------------------------------------------------------------------
# Pure unit tests — get_daily_prompt
# ---------------------------------------------------------------------------


class TestGetDailyPrompt:
    @pytest.fixture(autouse=True)
    async def clean_db(self):
        yield

    @pytest.fixture(autouse=True)
    def mock_email(self):
        yield

    def test_deterministic_same_user_same_date(self):
        d = date(2026, 5, 1)
        p1 = get_daily_prompt(user_id=42, today=d)
        p2 = get_daily_prompt(user_id=42, today=d)
        assert p1["id"] == p2["id"]

    def test_different_users_likely_different_prompt(self):
        """Hash of different user_ids on same day should produce different indices most of the time."""
        d = date(2026, 5, 1)
        results = {get_daily_prompt(user_id=uid, today=d)["id"] for uid in range(1, 20)}
        # With 32 prompts and 19 users at least some variation is expected
        assert len(results) > 1

    def test_returns_dict_with_required_fields(self):
        d = date(2026, 6, 1)
        prompt = get_daily_prompt(user_id=1, today=d)
        assert "id" in prompt
        assert "topic" in prompt
        assert "text" in prompt

    def test_prompt_from_known_list(self):
        d = date(2026, 6, 1)
        prompt = get_daily_prompt(user_id=1, today=d)
        ids = [p["id"] for p in _PROMPTS]
        assert prompt["id"] in ids

    def test_none_today_uses_current_date(self):
        """Should not raise; result should be a valid prompt."""
        prompt = get_daily_prompt(user_id=1)
        assert "id" in prompt

    def test_different_dates_same_user_can_differ(self):
        d1 = date(2026, 5, 1)
        d2 = date(2026, 5, 2)
        p1 = get_daily_prompt(user_id=1, today=d1)
        p2 = get_daily_prompt(user_id=1, today=d2)
        # Different dates: not guaranteed to differ, but we can at least confirm no crash
        assert isinstance(p1["id"], int)
        assert isinstance(p2["id"], int)


# ---------------------------------------------------------------------------
# Pure unit tests — get_next_prompt
# ---------------------------------------------------------------------------


class TestGetNextPrompt:
    @pytest.fixture(autouse=True)
    async def clean_db(self):
        yield

    @pytest.fixture(autouse=True)
    def mock_email(self):
        yield

    def test_next_after_id_1_is_id_2(self):
        result = get_next_prompt(current_id=1)
        assert result["id"] == 2

    def test_next_after_last_wraps_to_first(self):
        last_id = _PROMPTS[-1]["id"]
        result = get_next_prompt(current_id=last_id)
        assert result["id"] == _PROMPTS[0]["id"]

    def test_invalid_id_wraps_gracefully(self):
        """Invalid id → idx=-1 → next is index 0."""
        result = get_next_prompt(current_id=9999)
        assert result["id"] == _PROMPTS[0]["id"]

    def test_next_middle_prompt(self):
        mid = _PROMPTS[15]["id"]
        result = get_next_prompt(current_id=mid)
        assert result["id"] == _PROMPTS[16]["id"]

    def test_returns_dict_with_required_fields(self):
        result = get_next_prompt(current_id=1)
        for field in ("id", "topic", "text"):
            assert field in result


# ---------------------------------------------------------------------------
# Pure unit tests — list_by_topic
# ---------------------------------------------------------------------------


class TestListByTopic:
    @pytest.fixture(autouse=True)
    async def clean_db(self):
        yield

    @pytest.fixture(autouse=True)
    def mock_email(self):
        yield

    def test_none_returns_all_prompts(self):
        result = list_by_topic(None)
        assert len(result) == _TOTAL_PROMPTS

    def test_work_stress_returns_8(self):
        result = list_by_topic("work_stress")
        assert len(result) == 8
        assert all(p["topic"] == "work_stress" for p in result)

    def test_relationships_returns_8(self):
        result = list_by_topic("relationships")
        assert len(result) == 8
        assert all(p["topic"] == "relationships" for p in result)

    def test_self_compassion_returns_8(self):
        result = list_by_topic("self_compassion")
        assert len(result) == 8
        assert all(p["topic"] == "self_compassion" for p in result)

    def test_gratitude_returns_8(self):
        result = list_by_topic("gratitude")
        assert len(result) == 8
        assert all(p["topic"] == "gratitude" for p in result)

    def test_unknown_topic_returns_empty(self):
        result = list_by_topic("nonexistent_topic")
        assert result == []


# ---------------------------------------------------------------------------
# API integration tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_daily_prompt_requires_auth(client: AsyncClient):
    resp = await client.get("/api/v1/journal/prompts/daily")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_next_prompt_requires_auth(client: AsyncClient):
    resp = await client.get("/api/v1/journal/prompts/next?current_id=1")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_list_prompts_requires_auth(client: AsyncClient):
    resp = await client.get("/api/v1/journal/prompts")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_daily_prompt_returns_prompt_and_topics(client: AsyncClient):
    email = f"prompts_daily@{TEST_EMAIL_DOMAIN}"
    token = await _register_and_login(client, email)
    resp = await client.get("/api/v1/journal/prompts/daily", headers=_auth_header(token))
    assert resp.status_code == 200
    data = resp.json()
    assert "prompt" in data
    assert "topics" in data
    for field in ("id", "topic", "text"):
        assert field in data["prompt"]
    assert isinstance(data["topics"], list)
    assert len(data["topics"]) == 4


@pytest.mark.asyncio
async def test_daily_prompt_deterministic_same_user(client: AsyncClient):
    email = f"prompts_determ@{TEST_EMAIL_DOMAIN}"
    token = await _register_and_login(client, email)
    headers = _auth_header(token)
    resp1 = await client.get("/api/v1/journal/prompts/daily", headers=headers)
    resp2 = await client.get("/api/v1/journal/prompts/daily", headers=headers)
    assert resp1.json()["prompt"]["id"] == resp2.json()["prompt"]["id"]


@pytest.mark.asyncio
async def test_next_prompt_returns_successor(client: AsyncClient):
    email = f"prompts_next@{TEST_EMAIL_DOMAIN}"
    token = await _register_and_login(client, email)
    resp = await client.get("/api/v1/journal/prompts/next?current_id=1", headers=_auth_header(token))
    assert resp.status_code == 200
    data = resp.json()
    assert data["id"] == 2


@pytest.mark.asyncio
async def test_next_prompt_wraps_at_end(client: AsyncClient):
    email = f"prompts_wrap@{TEST_EMAIL_DOMAIN}"
    token = await _register_and_login(client, email)
    last_id = _PROMPTS[-1]["id"]
    resp = await client.get(f"/api/v1/journal/prompts/next?current_id={last_id}", headers=_auth_header(token))
    assert resp.status_code == 200
    assert resp.json()["id"] == _PROMPTS[0]["id"]


@pytest.mark.asyncio
async def test_list_all_prompts(client: AsyncClient):
    email = f"prompts_list@{TEST_EMAIL_DOMAIN}"
    token = await _register_and_login(client, email)
    resp = await client.get("/api/v1/journal/prompts", headers=_auth_header(token))
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == _TOTAL_PROMPTS


@pytest.mark.asyncio
async def test_list_prompts_filtered_by_topic(client: AsyncClient):
    email = f"prompts_filter@{TEST_EMAIL_DOMAIN}"
    token = await _register_and_login(client, email)
    resp = await client.get("/api/v1/journal/prompts?topic=gratitude", headers=_auth_header(token))
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 8
    assert all(p["topic"] == "gratitude" for p in data)


@pytest.mark.asyncio
async def test_list_prompts_unknown_topic_returns_empty(client: AsyncClient):
    email = f"prompts_unknown@{TEST_EMAIL_DOMAIN}"
    token = await _register_and_login(client, email)
    resp = await client.get("/api/v1/journal/prompts?topic=unknown_topic", headers=_auth_header(token))
    assert resp.status_code == 200
    assert resp.json() == []
