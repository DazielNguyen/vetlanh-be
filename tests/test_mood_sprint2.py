"""
Tests for Epic E3 Mood Tracker Sprint 2 — Mood Trend API (US-012).

Covers:
  Service unit tests (no real DB — AsyncMock):
    - get_trend: week period returns 7 slots
    - get_trend: month period returns 30 slots
    - get_trend: slots are ascending by date
    - get_trend: empty range → best_day=None, worst_day=None, average_mood=None
    - get_trend: best_day is date with highest mood (tie → earliest)
    - get_trend: worst_day is date with lowest mood (tie → earliest)
    - get_trend: average_mood is rounded to 2 decimal places
    - get_trend: days with no entry have mood=None, energy=None, factors=[], note=None

  API integration tests (real DB, in-process HTTP via AsyncClient):
    - GET /mood/trend?period=week → 200, 7 entries
    - GET /mood/trend?period=month → 200, 30 entries
    - GET /mood/trend (default) → 200, 7 entries (defaults to week)
    - GET /mood/trend?period=week with no entries → best_day=null, worst_day=null, average_mood=null
    - GET /mood/trend without auth → 401
    - Create entry for today, then check today's slot has mood != null
    - Entries are isolated per user
    - Response contains required fields
"""

from datetime import date, datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import AsyncClient

from app.schemas.mood import MoodTrendEntry, MoodTrendResponse
from app.services.mood import get_trend


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

TEST_EMAIL_DOMAIN = "test.vetlanh"
_TODAY = date(2026, 6, 1)


def _make_mood_orm_mock(
    *,
    user_id: int = 1,
    entry_date: date = _TODAY,
    mood: int = 3,
    energy: str = "medium",
    factors: list[str] | None = None,
    note: str | None = None,
) -> MagicMock:
    if factors is None:
        factors = []
    m = MagicMock()
    m.id = 1
    m.user_id = user_id
    m.date = entry_date
    m.mood = mood
    m.energy = energy
    m.factors = factors
    m.note = note
    m.created_at = datetime.now(tz=timezone.utc)
    m.updated_at = datetime.now(tz=timezone.utc)
    return m


def _make_trend_db(entries: list) -> AsyncMock:
    scalars_mock = MagicMock()
    scalars_mock.all.return_value = entries

    result_mock = MagicMock()
    result_mock.scalars.return_value = scalars_mock

    db = AsyncMock()
    db.execute = AsyncMock(return_value=result_mock)
    return db


# ---------------------------------------------------------------------------
# Override autouse conftest fixtures for pure unit test classes
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Service unit tests — get_trend
# ---------------------------------------------------------------------------


class TestGetTrendService:
    @pytest.fixture(autouse=True)
    async def clean_db(self):  # noqa: F811
        yield

    @pytest.fixture(autouse=True)
    def mock_email(self):  # noqa: F811
        yield

    async def test_week_period_returns_7_slots(self):
        db = _make_trend_db([])
        result = await get_trend(db, user_id=1, period="week")
        assert len(result.entries) == 7

    async def test_month_period_returns_30_slots(self):
        db = _make_trend_db([])
        result = await get_trend(db, user_id=1, period="month")
        assert len(result.entries) == 30

    async def test_week_period_field_is_week(self):
        db = _make_trend_db([])
        result = await get_trend(db, user_id=1, period="week")
        assert result.period == "week"

    async def test_month_period_field_is_month(self):
        db = _make_trend_db([])
        result = await get_trend(db, user_id=1, period="month")
        assert result.period == "month"

    async def test_slots_are_ascending_by_date(self):
        db = _make_trend_db([])
        result = await get_trend(db, user_id=1, period="week")
        dates = [e.date for e in result.entries]
        assert dates == sorted(dates)

    async def test_week_start_is_today_minus_6(self):
        db = _make_trend_db([])
        result = await get_trend(db, user_id=1, period="week")
        today = datetime.now(tz=timezone.utc).date()
        assert result.start == today - timedelta(days=6)

    async def test_week_end_is_today(self):
        db = _make_trend_db([])
        result = await get_trend(db, user_id=1, period="week")
        today = datetime.now(tz=timezone.utc).date()
        assert result.end == today

    async def test_month_start_is_today_minus_29(self):
        db = _make_trend_db([])
        result = await get_trend(db, user_id=1, period="month")
        today = datetime.now(tz=timezone.utc).date()
        assert result.start == today - timedelta(days=29)

    async def test_empty_range_best_day_is_none(self):
        db = _make_trend_db([])
        result = await get_trend(db, user_id=1, period="week")
        assert result.best_day is None

    async def test_empty_range_worst_day_is_none(self):
        db = _make_trend_db([])
        result = await get_trend(db, user_id=1, period="week")
        assert result.worst_day is None

    async def test_empty_range_average_mood_is_none(self):
        db = _make_trend_db([])
        result = await get_trend(db, user_id=1, period="week")
        assert result.average_mood is None

    async def test_days_with_no_entry_have_null_mood(self):
        db = _make_trend_db([])
        result = await get_trend(db, user_id=1, period="week")
        # All slots should have mood=None
        assert all(e.mood is None for e in result.entries)

    async def test_days_with_no_entry_have_null_energy(self):
        db = _make_trend_db([])
        result = await get_trend(db, user_id=1, period="week")
        assert all(e.energy is None for e in result.entries)

    async def test_days_with_no_entry_have_empty_factors(self):
        db = _make_trend_db([])
        result = await get_trend(db, user_id=1, period="week")
        assert all(e.factors == [] for e in result.entries)

    async def test_days_with_no_entry_have_null_note(self):
        db = _make_trend_db([])
        result = await get_trend(db, user_id=1, period="week")
        assert all(e.note is None for e in result.entries)

    async def test_best_day_is_highest_mood_date(self):
        today = datetime.now(tz=timezone.utc).date()
        # Entry 2 days ago with mood=5 (best)
        best_date = today - timedelta(days=2)
        worst_date = today - timedelta(days=4)
        entries = [
            _make_mood_orm_mock(entry_date=best_date, mood=5),
            _make_mood_orm_mock(entry_date=worst_date, mood=2),
        ]
        db = _make_trend_db(entries)
        result = await get_trend(db, user_id=1, period="week")
        assert result.best_day == best_date

    async def test_worst_day_is_lowest_mood_date(self):
        today = datetime.now(tz=timezone.utc).date()
        best_date = today - timedelta(days=2)
        worst_date = today - timedelta(days=4)
        entries = [
            _make_mood_orm_mock(entry_date=best_date, mood=5),
            _make_mood_orm_mock(entry_date=worst_date, mood=2),
        ]
        db = _make_trend_db(entries)
        result = await get_trend(db, user_id=1, period="week")
        assert result.worst_day == worst_date

    async def test_best_day_tie_goes_to_earliest(self):
        """When two entries share the highest mood, best_day = the earlier date."""
        today = datetime.now(tz=timezone.utc).date()
        early = today - timedelta(days=5)
        late = today - timedelta(days=1)
        entries = [
            _make_mood_orm_mock(entry_date=early, mood=5),
            _make_mood_orm_mock(entry_date=late, mood=5),
        ]
        db = _make_trend_db(entries)
        result = await get_trend(db, user_id=1, period="week")
        assert result.best_day == early

    async def test_worst_day_tie_goes_to_earliest(self):
        """When two entries share the lowest mood, worst_day = the earlier date."""
        today = datetime.now(tz=timezone.utc).date()
        early = today - timedelta(days=5)
        late = today - timedelta(days=1)
        entries = [
            _make_mood_orm_mock(entry_date=early, mood=1),
            _make_mood_orm_mock(entry_date=late, mood=1),
        ]
        db = _make_trend_db(entries)
        result = await get_trend(db, user_id=1, period="week")
        assert result.worst_day == early

    async def test_average_mood_is_correct(self):
        """average_mood should equal mean of present moods, rounded to 2dp."""
        today = datetime.now(tz=timezone.utc).date()
        entries = [
            _make_mood_orm_mock(entry_date=today - timedelta(days=2), mood=3),
            _make_mood_orm_mock(entry_date=today - timedelta(days=1), mood=4),
            _make_mood_orm_mock(entry_date=today, mood=5),
        ]
        db = _make_trend_db(entries)
        result = await get_trend(db, user_id=1, period="week")
        assert result.average_mood == round((3 + 4 + 5) / 3, 2)

    async def test_average_mood_rounded_2dp(self):
        """(1+2+3+4+5) / 5 = 3.0 — check rounding works for non-trivial average."""
        today = datetime.now(tz=timezone.utc).date()
        entries = [
            _make_mood_orm_mock(entry_date=today - timedelta(days=i), mood=v)
            for i, v in enumerate([1, 2, 4])
        ]
        db = _make_trend_db(entries)
        result = await get_trend(db, user_id=1, period="week")
        assert result.average_mood == round((1 + 2 + 4) / 3, 2)

    async def test_entry_date_within_range_populates_slot(self):
        """An existing entry's mood value should appear in the corresponding slot."""
        today = datetime.now(tz=timezone.utc).date()
        target = today - timedelta(days=3)
        entries = [_make_mood_orm_mock(entry_date=target, mood=4)]
        db = _make_trend_db(entries)
        result = await get_trend(db, user_id=1, period="week")
        slot = next(e for e in result.entries if e.date == target)
        assert slot.mood == 4

    async def test_single_entry_best_and_worst_same_date(self):
        today = datetime.now(tz=timezone.utc).date()
        entries = [_make_mood_orm_mock(entry_date=today, mood=3)]
        db = _make_trend_db(entries)
        result = await get_trend(db, user_id=1, period="week")
        assert result.best_day == today
        assert result.worst_day == today


# ---------------------------------------------------------------------------
# Integration test helpers
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
# API integration tests — GET /mood/trend
# ---------------------------------------------------------------------------


class TestGetMoodTrend:
    async def test_unauthenticated_returns_401(self, client: AsyncClient):
        resp = await client.get("/api/v1/mood/trend?period=week")
        assert resp.status_code == 401

    async def test_week_returns_200(self, client: AsyncClient):
        token = await _register_and_login(client, "trend_week_200@test.vetlanh")
        resp = await client.get("/api/v1/mood/trend?period=week", headers=_auth_header(token))
        assert resp.status_code == 200

    async def test_week_returns_7_entries(self, client: AsyncClient):
        token = await _register_and_login(client, "trend_week_7@test.vetlanh")
        resp = await client.get("/api/v1/mood/trend?period=week", headers=_auth_header(token))
        assert resp.status_code == 200
        assert len(resp.json()["entries"]) == 7

    async def test_month_returns_200(self, client: AsyncClient):
        token = await _register_and_login(client, "trend_month_200@test.vetlanh")
        resp = await client.get("/api/v1/mood/trend?period=month", headers=_auth_header(token))
        assert resp.status_code == 200

    async def test_month_returns_30_entries(self, client: AsyncClient):
        token = await _register_and_login(client, "trend_month_30@test.vetlanh")
        resp = await client.get("/api/v1/mood/trend?period=month", headers=_auth_header(token))
        assert resp.status_code == 200
        assert len(resp.json()["entries"]) == 30

    async def test_default_period_returns_7_entries(self, client: AsyncClient):
        """Omitting ?period= defaults to week → 7 entries."""
        token = await _register_and_login(client, "trend_default@test.vetlanh")
        resp = await client.get("/api/v1/mood/trend", headers=_auth_header(token))
        assert resp.status_code == 200
        assert len(resp.json()["entries"]) == 7

    async def test_no_entries_best_day_is_null(self, client: AsyncClient):
        token = await _register_and_login(client, "trend_empty_best@test.vetlanh")
        resp = await client.get("/api/v1/mood/trend?period=week", headers=_auth_header(token))
        assert resp.json()["best_day"] is None

    async def test_no_entries_worst_day_is_null(self, client: AsyncClient):
        token = await _register_and_login(client, "trend_empty_worst@test.vetlanh")
        resp = await client.get("/api/v1/mood/trend?period=week", headers=_auth_header(token))
        assert resp.json()["worst_day"] is None

    async def test_no_entries_average_mood_is_null(self, client: AsyncClient):
        token = await _register_and_login(client, "trend_empty_avg@test.vetlanh")
        resp = await client.get("/api/v1/mood/trend?period=week", headers=_auth_header(token))
        assert resp.json()["average_mood"] is None

    async def test_today_slot_has_mood_after_checkin(self, client: AsyncClient):
        """After creating a mood entry for today, the trend slot for today has mood != null."""
        token = await _register_and_login(client, "trend_today@test.vetlanh")
        headers = _auth_header(token)
        today_str = datetime.now(tz=timezone.utc).date().isoformat()

        await client.post(
            "/api/v1/mood/entries",
            json={"date": today_str, "mood": 4, "energy": "high", "factors": [], "note": None},
            headers=headers,
        )

        resp = await client.get("/api/v1/mood/trend?period=week", headers=headers)
        assert resp.status_code == 200
        entries = resp.json()["entries"]
        today_slot = next((e for e in entries if e["date"] == today_str), None)
        assert today_slot is not None
        assert today_slot["mood"] == 4

    async def test_trend_isolated_per_user(self, client: AsyncClient):
        """User A's check-in must not affect User B's trend."""
        token_a = await _register_and_login(client, "trend_usera@test.vetlanh")
        token_b = await _register_and_login(client, "trend_userb@test.vetlanh")
        today_str = datetime.now(tz=timezone.utc).date().isoformat()

        await client.post(
            "/api/v1/mood/entries",
            json={"date": today_str, "mood": 5, "energy": "high", "factors": [], "note": None},
            headers=_auth_header(token_a),
        )

        resp = await client.get("/api/v1/mood/trend?period=week", headers=_auth_header(token_b))
        assert resp.json()["average_mood"] is None

    async def test_response_contains_required_top_level_fields(self, client: AsyncClient):
        token = await _register_and_login(client, "trend_fields@test.vetlanh")
        resp = await client.get("/api/v1/mood/trend?period=week", headers=_auth_header(token))
        data = resp.json()
        for field in ("period", "start", "end", "entries", "best_day", "worst_day", "average_mood"):
            assert field in data, f"Missing field: {field}"

    async def test_entry_slots_contain_required_fields(self, client: AsyncClient):
        token = await _register_and_login(client, "trend_slot_fields@test.vetlanh")
        resp = await client.get("/api/v1/mood/trend?period=week", headers=_auth_header(token))
        slot = resp.json()["entries"][0]
        for field in ("date", "mood", "energy", "factors", "note"):
            assert field in slot, f"Missing slot field: {field}"

    async def test_invalid_bearer_token_returns_401(self, client: AsyncClient):
        resp = await client.get(
            "/api/v1/mood/trend",
            headers={"Authorization": "Bearer bad.token.here"},
        )
        assert resp.status_code == 401

    async def test_week_entries_are_ascending(self, client: AsyncClient):
        """Slots must be ordered oldest → newest (ascending)."""
        token = await _register_and_login(client, "trend_asc@test.vetlanh")
        resp = await client.get("/api/v1/mood/trend?period=week", headers=_auth_header(token))
        dates = [e["date"] for e in resp.json()["entries"]]
        assert dates == sorted(dates)
