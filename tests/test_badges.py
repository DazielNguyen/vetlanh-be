"""
Tests for US-027 — Badge milestones.

Covers:
  Service unit tests (mocked DB):
    - _compute_streak: empty entries → 0
    - _compute_streak: single entry → 1
    - _compute_streak: 3 consecutive days → 3
    - _compute_streak: gap breaks streak at correct point
    - _compute_streak: duplicate dates count as one day
    - get_badges: streak < smallest milestone → all badges unlocked=False, is_new=False
    - get_badges: streak >= 3 → first-flame unlocked, is_new=True on first call
    - get_badges: second call same milestone → is_new=False (already notified)
    - get_badges: multiple milestones reached → only new ones marked is_new=True
    - get_badges: response includes streak_days field equal to computed streak
    - get_badges: badges list includes all 5 milestones

  API integration tests (real DB via AsyncClient):
    - GET /api/v1/badges → 401 without token
    - GET /api/v1/badges → 200 with correct response shape
    - GET /api/v1/badges → streak=0, all badges unlocked=False for fresh user
    - GET /api/v1/badges → is_new=True on first call after milestone, is_new=False on second call
"""

from datetime import date, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import AsyncClient

from app.schemas.badge import BadgeOut, BadgesResponse
from app.services.badge import _compute_streak, get_badges

TEST_EMAIL_DOMAIN = "test.vetlanh"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_mood_entry(d: date) -> MagicMock:
    m = MagicMock()
    m.date = d
    return m


def _make_db_mock(entries=None, already_notified=None):
    """Build an AsyncMock db that returns given mood entries and notified milestones."""
    entries = entries or []
    already_notified = already_notified or []

    # First execute call → mood entries; second → already_notified milestones
    async def side_effect(query):
        # We can't easily distinguish calls without inspecting query, so we use a counter
        side_effect._call_count = getattr(side_effect, "_call_count", 0) + 1
        result = MagicMock()
        if side_effect._call_count == 1:
            scalars = MagicMock()
            scalars.all.return_value = entries
            result.scalars.return_value = scalars
        else:
            scalars = MagicMock()
            scalars.all.return_value = already_notified
            result.scalars.return_value = scalars
        return result

    db = AsyncMock()
    db.execute = AsyncMock(side_effect=side_effect)
    db.add = MagicMock()
    db.flush = AsyncMock()
    return db


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
# Pure unit tests — _compute_streak
# ---------------------------------------------------------------------------


class TestComputeStreak:
    """No DB needed — pure function."""

    @pytest.fixture(autouse=True)
    async def clean_db(self):
        yield

    @pytest.fixture(autouse=True)
    def mock_email(self):
        yield

    def test_empty_entries_returns_zero(self):
        assert _compute_streak([]) == 0

    def test_single_entry_returns_one(self):
        entries = [_make_mood_entry(date(2026, 5, 1))]
        assert _compute_streak(entries) == 1

    def test_three_consecutive_days(self):
        today = date(2026, 5, 3)
        entries = [
            _make_mood_entry(today),
            _make_mood_entry(today - timedelta(days=1)),
            _make_mood_entry(today - timedelta(days=2)),
        ]
        assert _compute_streak(entries) == 3

    def test_gap_breaks_streak(self):
        """Day 3, Day 2, Day 0 (gap on day 1) — streak should be 2 then break."""
        today = date(2026, 5, 5)
        entries = [
            _make_mood_entry(today),
            _make_mood_entry(today - timedelta(days=1)),
            # gap: missing day -2
            _make_mood_entry(today - timedelta(days=3)),
        ]
        assert _compute_streak(entries) == 2

    def test_duplicate_dates_count_once(self):
        today = date(2026, 5, 3)
        entries = [
            _make_mood_entry(today),
            _make_mood_entry(today),  # duplicate
            _make_mood_entry(today - timedelta(days=1)),
        ]
        assert _compute_streak(entries) == 2


# ---------------------------------------------------------------------------
# Service unit tests — get_badges
# ---------------------------------------------------------------------------


class TestGetBadgesService:
    """Unit tests for get_badges with mocked DB."""

    @pytest.fixture(autouse=True)
    async def clean_db(self):
        yield

    @pytest.fixture(autouse=True)
    def mock_email(self):
        yield

    @pytest.mark.asyncio
    async def test_no_entries_all_badges_locked(self):
        db = _make_db_mock(entries=[], already_notified=[])
        result = await get_badges(db, user_id=1)
        assert result.streak_days == 0
        assert all(not b.unlocked for b in result.badges)
        assert all(not b.is_new for b in result.badges)

    @pytest.mark.asyncio
    async def test_streak_3_first_flame_unlocked_and_new(self):
        today = date.today()
        entries = [_make_mood_entry(today - timedelta(days=i)) for i in range(3)]
        db = _make_db_mock(entries=entries, already_notified=[])
        result = await get_badges(db, user_id=1)
        assert result.streak_days == 3
        first_flame = next(b for b in result.badges if b.slug == "first-flame")
        assert first_flame.unlocked is True
        assert first_flame.is_new is True

    @pytest.mark.asyncio
    async def test_second_call_same_milestone_is_new_false(self):
        today = date.today()
        entries = [_make_mood_entry(today - timedelta(days=i)) for i in range(3)]
        # Simulate that milestone 3 was already notified
        db = _make_db_mock(entries=entries, already_notified=[3])
        result = await get_badges(db, user_id=1)
        first_flame = next(b for b in result.badges if b.slug == "first-flame")
        assert first_flame.unlocked is True
        assert first_flame.is_new is False

    @pytest.mark.asyncio
    async def test_new_milestones_persisted(self):
        """When is_new milestones exist, db.add should be called and db.flush awaited."""
        today = date.today()
        entries = [_make_mood_entry(today - timedelta(days=i)) for i in range(3)]
        db = _make_db_mock(entries=entries, already_notified=[])
        await get_badges(db, user_id=1)
        db.add.assert_called()
        db.flush.assert_awaited()

    @pytest.mark.asyncio
    async def test_no_new_milestones_no_flush(self):
        db = _make_db_mock(entries=[], already_notified=[])
        await get_badges(db, user_id=1)
        db.flush.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_badges_list_has_five_entries(self):
        db = _make_db_mock(entries=[], already_notified=[])
        result = await get_badges(db, user_id=1)
        assert len(result.badges) == 5

    @pytest.mark.asyncio
    async def test_all_expected_slugs_present(self):
        db = _make_db_mock(entries=[], already_notified=[])
        result = await get_badges(db, user_id=1)
        slugs = {b.slug for b in result.badges}
        assert slugs == {"first-flame", "week-warrior", "habit-builder", "monthly-champion", "resilience-master"}

    @pytest.mark.asyncio
    async def test_streak_7_week_warrior_unlocked(self):
        today = date.today()
        entries = [_make_mood_entry(today - timedelta(days=i)) for i in range(7)]
        db = _make_db_mock(entries=entries, already_notified=[])
        result = await get_badges(db, user_id=1)
        week_warrior = next(b for b in result.badges if b.slug == "week-warrior")
        assert week_warrior.unlocked is True
        assert week_warrior.is_new is True
        # first-flame is also new
        first_flame = next(b for b in result.badges if b.slug == "first-flame")
        assert first_flame.unlocked is True
        assert first_flame.is_new is True

    @pytest.mark.asyncio
    async def test_partial_already_notified(self):
        """first-flame notified, week-warrior is new."""
        today = date.today()
        entries = [_make_mood_entry(today - timedelta(days=i)) for i in range(7)]
        db = _make_db_mock(entries=entries, already_notified=[3])
        result = await get_badges(db, user_id=1)
        first_flame = next(b for b in result.badges if b.slug == "first-flame")
        week_warrior = next(b for b in result.badges if b.slug == "week-warrior")
        assert first_flame.is_new is False
        assert week_warrior.is_new is True


# ---------------------------------------------------------------------------
# API integration tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_badges_requires_auth(client: AsyncClient):
    resp = await client.get("/api/v1/badges")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_badges_fresh_user_zero_streak(client: AsyncClient):
    email = f"badge_fresh@{TEST_EMAIL_DOMAIN}"
    token = await _register_and_login(client, email)
    resp = await client.get("/api/v1/badges", headers=_auth_header(token))
    assert resp.status_code == 200
    data = resp.json()
    assert data["streak_days"] == 0
    assert len(data["badges"]) == 5
    assert all(not b["unlocked"] for b in data["badges"])


@pytest.mark.asyncio
async def test_badges_response_shape(client: AsyncClient):
    email = f"badge_shape@{TEST_EMAIL_DOMAIN}"
    token = await _register_and_login(client, email)
    resp = await client.get("/api/v1/badges", headers=_auth_header(token))
    assert resp.status_code == 200
    data = resp.json()
    assert "streak_days" in data
    assert "badges" in data
    badge = data["badges"][0]
    for field in ("slug", "label", "milestone_days", "unlocked", "is_new"):
        assert field in badge


@pytest.mark.asyncio
async def test_badges_is_new_transitions(client: AsyncClient):
    """After posting 3 mood entries: first call → is_new=True; second call → is_new=False."""
    email = f"badge_isnew@{TEST_EMAIL_DOMAIN}"
    token = await _register_and_login(client, email)
    headers = _auth_header(token)

    today = date.today()
    for i in range(3):
        d = today - timedelta(days=i)
        resp = await client.post(
            "/api/v1/mood/entries",
            json={"date": d.isoformat(), "mood": 3, "energy": "medium", "factors": [], "note": None},
            headers=headers,
        )
        assert resp.status_code == 201

    # First call — first-flame should be is_new=True
    resp1 = await client.get("/api/v1/badges", headers=headers)
    assert resp1.status_code == 200
    badges1 = {b["slug"]: b for b in resp1.json()["badges"]}
    assert badges1["first-flame"]["unlocked"] is True
    assert badges1["first-flame"]["is_new"] is True

    # Second call — is_new should now be False
    resp2 = await client.get("/api/v1/badges", headers=headers)
    assert resp2.status_code == 200
    badges2 = {b["slug"]: b for b in resp2.json()["badges"]}
    assert badges2["first-flame"]["unlocked"] is True
    assert badges2["first-flame"]["is_new"] is False
