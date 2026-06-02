"""
Tests for Dashboard feature — US-026.

Covers:
  Service unit tests:
    _greeting:
      - local hour < 12 → "Buổi sáng tốt lành, {name}!"
      - local hour 12-17 → "Buổi chiều vui vẻ, {name}!"
      - local hour >= 18 → "Buổi tối bình yên, {name}!"
      - display_name None → uses "bạn"
      - display_name provided → used in greeting

    _compute_streak:
      - empty list → 0
      - single entry → 1
      - two consecutive days → 2
      - three consecutive days → 3
      - gap of 2 days resets streak → counts only latest consecutive run
      - multiple entries same day count as one
      - streak only counts from most recent date backwards

    get_dashboard:
      - checked_in_today=True only when today has an entry
      - checked_in_today=False when no entry today
      - mood_sparkline has exactly 7 items
      - sparkline ordered oldest → newest
      - sparkline mood=None for days with no entry
      - sparkline mood set for days with entry
      - today_mood is None when no check-in today
      - streak_days passed from _compute_streak
      - recommended_exercises is a list of up to 3 items
      - mood 1 → sad filter; mood 3 → anxious; mood 5 → need_energy
      - no entries → anxious fallback

  API integration tests:
    Auth:
      - GET /dashboard → 401 without token
      - GET /dashboard → 401 with invalid token

    GET /dashboard:
      - 200 with correct shape
      - greeting is a non-empty string
      - checked_in_today=False for fresh user
      - streak_days=0 for fresh user
      - mood_sparkline has exactly 7 items
      - today_mood=null for fresh user
      - checked_in_today=True after mood check-in
      - recommended_exercises is a list
      - sparkline contains today's date
"""

import unittest.mock as mock
from datetime import date, datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import AsyncClient

from app.services.dashboard import _compute_streak, _greeting

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

TEST_EMAIL_DOMAIN = "test.vetlanh"


def _make_mood_entry(*, date_val: date, mood: int = 3, user_id: int = 1) -> MagicMock:
    m = MagicMock(spec=["date", "mood", "user_id", "id", "note", "energy", "factors", "created_at", "updated_at"])
    m.date = date_val
    m.mood = mood
    m.user_id = user_id
    m.id = 1
    m.note = None
    m.energy = None
    m.factors = []
    m.created_at = datetime.now(tz=timezone.utc)
    m.updated_at = datetime.now(tz=timezone.utc)
    return m


async def _register_and_login(client: AsyncClient, email: str) -> str:
    captured = []

    async def capture(*args, **kwargs):
        captured.append(args)

    with mock.patch(
        "app.api.v1.endpoints.auth.send_verification_email",
        side_effect=capture,
    ):
        await client.post(
            "/api/v1/auth/register",
            json={"email": email, "password": "securepass1"},
        )

    token = captured[0][1]
    await client.get(f"/api/v1/auth/verify?token={token}")

    resp = await client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": "securepass1"},
    )
    assert resp.status_code == 200, f"Login failed: {resp.text}"
    return resp.json()["access_token"]


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


# ===========================================================================
# SERVICE UNIT TESTS — _greeting
# ===========================================================================


class TestGreeting:
    """Unit tests for _greeting() with UTC+7 Vietnam timezone logic."""

    def _utc_from_local(self, local_hour: int) -> datetime:
        """Return a Vietnam-timezone (UTC+7) datetime whose local hour equals *local_hour*.

        The mock replaces ``datetime`` in the dashboard module and returns this
        value directly.  The production code calls ``.hour`` on the result, so
        the datetime must carry the VN offset so that ``.hour`` equals the
        intended local hour.
        """
        _VN_TZ = timezone(timedelta(hours=7))
        return datetime(2024, 6, 1, local_hour, 0, 0, tzinfo=_VN_TZ)

    def test_morning_hour_0_returns_sang(self):
        fixed_dt = self._utc_from_local(0)
        with patch("app.services.dashboard.datetime") as mock_dt:
            mock_dt.now.return_value = fixed_dt
            result = _greeting("Minh")
        assert result == "Buổi sáng tốt lành, Minh!"

    def test_morning_hour_6_returns_sang(self):
        fixed_dt = self._utc_from_local(6)
        with patch("app.services.dashboard.datetime") as mock_dt:
            mock_dt.now.return_value = fixed_dt
            result = _greeting("Lan")
        assert result == "Buổi sáng tốt lành, Lan!"

    def test_morning_hour_11_returns_sang(self):
        fixed_dt = self._utc_from_local(11)
        with patch("app.services.dashboard.datetime") as mock_dt:
            mock_dt.now.return_value = fixed_dt
            result = _greeting("Nam")
        assert result == "Buổi sáng tốt lành, Nam!"

    def test_afternoon_hour_12_returns_chieu(self):
        fixed_dt = self._utc_from_local(12)
        with patch("app.services.dashboard.datetime") as mock_dt:
            mock_dt.now.return_value = fixed_dt
            result = _greeting("Hoa")
        assert result == "Buổi chiều vui vẻ, Hoa!"

    def test_afternoon_hour_15_returns_chieu(self):
        fixed_dt = self._utc_from_local(15)
        with patch("app.services.dashboard.datetime") as mock_dt:
            mock_dt.now.return_value = fixed_dt
            result = _greeting("Tuấn")
        assert result == "Buổi chiều vui vẻ, Tuấn!"

    def test_afternoon_hour_17_returns_chieu(self):
        fixed_dt = self._utc_from_local(17)
        with patch("app.services.dashboard.datetime") as mock_dt:
            mock_dt.now.return_value = fixed_dt
            result = _greeting("An")
        assert result == "Buổi chiều vui vẻ, An!"

    def test_evening_hour_18_returns_toi(self):
        fixed_dt = self._utc_from_local(18)
        with patch("app.services.dashboard.datetime") as mock_dt:
            mock_dt.now.return_value = fixed_dt
            result = _greeting("Bình")
        assert result == "Buổi tối bình yên, Bình!"

    def test_evening_hour_22_returns_toi(self):
        fixed_dt = self._utc_from_local(22)
        with patch("app.services.dashboard.datetime") as mock_dt:
            mock_dt.now.return_value = fixed_dt
            result = _greeting("Cường")
        assert result == "Buổi tối bình yên, Cường!"

    def test_none_display_name_uses_ban(self):
        fixed_dt = self._utc_from_local(9)
        with patch("app.services.dashboard.datetime") as mock_dt:
            mock_dt.now.return_value = fixed_dt
            result = _greeting(None)
        assert "bạn" in result

    def test_display_name_in_greeting(self):
        fixed_dt = self._utc_from_local(9)
        with patch("app.services.dashboard.datetime") as mock_dt:
            mock_dt.now.return_value = fixed_dt
            result = _greeting("TestUser")
        assert "TestUser" in result


# ===========================================================================
# SERVICE UNIT TESTS — _compute_streak
# ===========================================================================


class TestComputeStreak:

    def test_empty_list_returns_zero(self):
        assert _compute_streak([]) == 0

    def test_single_entry_returns_one(self):
        today = date.today()
        entry = _make_mood_entry(date_val=today)
        assert _compute_streak([entry]) == 1

    def test_two_consecutive_days_returns_two(self):
        today = date.today()
        yesterday = today - timedelta(days=1)
        entries = [
            _make_mood_entry(date_val=today),
            _make_mood_entry(date_val=yesterday),
        ]
        assert _compute_streak(entries) == 2

    def test_three_consecutive_days_returns_three(self):
        today = date.today()
        entries = [
            _make_mood_entry(date_val=today - timedelta(days=i))
            for i in range(3)
        ]
        assert _compute_streak(entries) == 3

    def test_gap_resets_streak(self):
        today = date.today()
        # today and 2 days ago — gap of 1 day in between
        entries = [
            _make_mood_entry(date_val=today),
            _make_mood_entry(date_val=today - timedelta(days=2)),
        ]
        # Streak from today = 1 (no yesterday)
        assert _compute_streak(entries) == 1

    def test_duplicate_dates_count_as_one(self):
        today = date.today()
        yesterday = today - timedelta(days=1)
        entries = [
            _make_mood_entry(date_val=today),
            _make_mood_entry(date_val=today),  # duplicate
            _make_mood_entry(date_val=yesterday),
        ]
        assert _compute_streak(entries) == 2

    def test_five_consecutive_days_returns_five(self):
        today = date.today()
        entries = [
            _make_mood_entry(date_val=today - timedelta(days=i))
            for i in range(5)
        ]
        assert _compute_streak(entries) == 5

    def test_streak_stops_at_first_gap(self):
        today = date.today()
        # Days 0, 1, 2, then gap, then days 5, 6
        entries = [
            _make_mood_entry(date_val=today),
            _make_mood_entry(date_val=today - timedelta(days=1)),
            _make_mood_entry(date_val=today - timedelta(days=2)),
            _make_mood_entry(date_val=today - timedelta(days=5)),
            _make_mood_entry(date_val=today - timedelta(days=6)),
        ]
        assert _compute_streak(entries) == 3


# ===========================================================================
# SERVICE UNIT TESTS — get_dashboard
# ===========================================================================


class TestGetDashboard:

    def _make_user(self, display_name: str | None = "TestUser") -> MagicMock:
        user = MagicMock()
        user.id = 1
        user.display_name = display_name
        return user

    def _make_db_with_entries(self, entries: list) -> AsyncMock:
        scalars_mock = MagicMock()
        scalars_mock.all.return_value = entries

        result_mock = MagicMock()
        result_mock.scalars.return_value = scalars_mock

        db = AsyncMock()
        db.execute = AsyncMock(return_value=result_mock)
        return db

    async def test_sparkline_has_seven_items(self):
        from app.services.dashboard import get_dashboard
        db = self._make_db_with_entries([])
        user = self._make_user()
        result = await get_dashboard(db, user)
        assert len(result.mood_sparkline) == 7

    async def test_checked_in_today_false_when_no_entries(self):
        from app.services.dashboard import get_dashboard
        db = self._make_db_with_entries([])
        user = self._make_user()
        result = await get_dashboard(db, user)
        assert result.checked_in_today is False

    async def test_checked_in_today_true_when_today_has_entry(self):
        from app.services.dashboard import get_dashboard
        today = datetime.now(tz=timezone.utc).date()
        entry = _make_mood_entry(date_val=today, mood=3)
        db = self._make_db_with_entries([entry])
        user = self._make_user()
        result = await get_dashboard(db, user)
        assert result.checked_in_today is True

    async def test_today_mood_none_when_no_entries(self):
        from app.services.dashboard import get_dashboard
        db = self._make_db_with_entries([])
        user = self._make_user()
        result = await get_dashboard(db, user)
        assert result.today_mood is None

    async def test_streak_days_zero_when_no_entries(self):
        from app.services.dashboard import get_dashboard
        db = self._make_db_with_entries([])
        user = self._make_user()
        result = await get_dashboard(db, user)
        assert result.streak_days == 0

    async def test_sparkline_ordered_oldest_to_newest(self):
        from app.services.dashboard import get_dashboard
        db = self._make_db_with_entries([])
        user = self._make_user()
        result = await get_dashboard(db, user)
        dates = [item.date for item in result.mood_sparkline]
        assert dates == sorted(dates)

    async def test_sparkline_mood_none_for_days_without_entry(self):
        from app.services.dashboard import get_dashboard
        db = self._make_db_with_entries([])
        user = self._make_user()
        result = await get_dashboard(db, user)
        for item in result.mood_sparkline:
            assert item.mood is None

    async def test_sparkline_mood_set_for_day_with_entry(self):
        from app.services.dashboard import get_dashboard
        today = datetime.now(tz=timezone.utc).date()
        entry = _make_mood_entry(date_val=today, mood=4)
        db = self._make_db_with_entries([entry])
        user = self._make_user()
        result = await get_dashboard(db, user)
        today_sparkline = next(s for s in result.mood_sparkline if s.date == today)
        assert today_sparkline.mood == 4

    async def test_recommended_exercises_is_list(self):
        from app.services.dashboard import get_dashboard
        db = self._make_db_with_entries([])
        user = self._make_user()
        result = await get_dashboard(db, user)
        assert isinstance(result.recommended_exercises, list)

    async def test_recommended_exercises_at_most_three(self):
        from app.services.dashboard import get_dashboard
        db = self._make_db_with_entries([])
        user = self._make_user()
        result = await get_dashboard(db, user)
        assert len(result.recommended_exercises) <= 3

    async def test_no_entries_uses_anxious_fallback(self):
        from app.services.dashboard import get_dashboard
        from app.schemas.exercise import MoodFilter

        db = self._make_db_with_entries([])
        user = self._make_user()

        with patch("app.services.dashboard.get_recommended") as mock_rec:
            mock_rec.return_value = []
            await get_dashboard(db, user)
            mock_rec.assert_called_once_with(mood=MoodFilter.anxious, limit=3)

    async def test_mood_1_uses_sad_filter(self):
        from app.services.dashboard import get_dashboard
        from app.schemas.exercise import MoodFilter

        today = datetime.now(tz=timezone.utc).date()
        entry = _make_mood_entry(date_val=today, mood=1)
        db = self._make_db_with_entries([entry])
        user = self._make_user()

        with patch("app.services.dashboard.get_recommended") as mock_rec:
            mock_rec.return_value = []
            await get_dashboard(db, user)
            mock_rec.assert_called_once_with(mood=MoodFilter.sad, limit=3)

    async def test_mood_3_uses_anxious_filter(self):
        from app.services.dashboard import get_dashboard
        from app.schemas.exercise import MoodFilter

        today = datetime.now(tz=timezone.utc).date()
        entry = _make_mood_entry(date_val=today, mood=3)
        db = self._make_db_with_entries([entry])
        user = self._make_user()

        with patch("app.services.dashboard.get_recommended") as mock_rec:
            mock_rec.return_value = []
            await get_dashboard(db, user)
            mock_rec.assert_called_once_with(mood=MoodFilter.anxious, limit=3)

    async def test_mood_5_uses_need_energy_filter(self):
        from app.services.dashboard import get_dashboard
        from app.schemas.exercise import MoodFilter

        today = datetime.now(tz=timezone.utc).date()
        entry = _make_mood_entry(date_val=today, mood=5)
        db = self._make_db_with_entries([entry])
        user = self._make_user()

        with patch("app.services.dashboard.get_recommended") as mock_rec:
            mock_rec.return_value = []
            await get_dashboard(db, user)
            mock_rec.assert_called_once_with(mood=MoodFilter.need_energy, limit=3)

    async def test_greeting_included_in_response(self):
        from app.services.dashboard import get_dashboard
        db = self._make_db_with_entries([])
        user = self._make_user(display_name="Minh")
        result = await get_dashboard(db, user)
        assert "Minh" in result.greeting

    async def test_fallback_to_latest_week_entry_when_no_today_entry(self):
        from app.services.dashboard import get_dashboard
        from app.schemas.exercise import MoodFilter

        today = datetime.now(tz=timezone.utc).date()
        yesterday = today - timedelta(days=1)
        # Only yesterday's entry, mood=2 → sad
        entry = _make_mood_entry(date_val=yesterday, mood=2)
        db = self._make_db_with_entries([entry])
        user = self._make_user()

        with patch("app.services.dashboard.get_recommended") as mock_rec:
            mock_rec.return_value = []
            await get_dashboard(db, user)
            mock_rec.assert_called_once_with(mood=MoodFilter.sad, limit=3)


# ===========================================================================
# API INTEGRATION TESTS
# ===========================================================================


class TestDashboardAPIAuth:

    async def test_get_without_token_returns_401(self, client: AsyncClient):
        resp = await client.get("/api/v1/dashboard")
        assert resp.status_code == 401

    async def test_invalid_bearer_token_returns_401(self, client: AsyncClient):
        resp = await client.get(
            "/api/v1/dashboard",
            headers={"Authorization": "Bearer invalid.token.here"},
        )
        assert resp.status_code == 401


class TestGetDashboardAPI:
    """GET /api/v1/dashboard"""

    async def test_returns_200(self, client: AsyncClient):
        token = await _register_and_login(client, "dash_200@test.vetlanh")
        resp = await client.get("/api/v1/dashboard", headers=_auth(token))
        assert resp.status_code == 200

    async def test_response_has_required_fields(self, client: AsyncClient):
        token = await _register_and_login(client, "dash_fields@test.vetlanh")
        resp = await client.get("/api/v1/dashboard", headers=_auth(token))
        data = resp.json()
        for field in ("greeting", "checked_in_today", "today_mood", "streak_days", "mood_sparkline", "recommended_exercises"):
            assert field in data, f"Missing field: {field}"

    async def test_greeting_is_non_empty_string(self, client: AsyncClient):
        token = await _register_and_login(client, "dash_greeting@test.vetlanh")
        resp = await client.get("/api/v1/dashboard", headers=_auth(token))
        greeting = resp.json()["greeting"]
        assert isinstance(greeting, str) and len(greeting) > 0

    async def test_checked_in_today_false_for_fresh_user(self, client: AsyncClient):
        token = await _register_and_login(client, "dash_noci@test.vetlanh")
        resp = await client.get("/api/v1/dashboard", headers=_auth(token))
        assert resp.json()["checked_in_today"] is False

    async def test_streak_days_zero_for_fresh_user(self, client: AsyncClient):
        token = await _register_and_login(client, "dash_streak0@test.vetlanh")
        resp = await client.get("/api/v1/dashboard", headers=_auth(token))
        assert resp.json()["streak_days"] == 0

    async def test_mood_sparkline_has_exactly_seven_items(self, client: AsyncClient):
        token = await _register_and_login(client, "dash_sparklen@test.vetlanh")
        resp = await client.get("/api/v1/dashboard", headers=_auth(token))
        assert len(resp.json()["mood_sparkline"]) == 7

    async def test_today_mood_null_for_fresh_user(self, client: AsyncClient):
        token = await _register_and_login(client, "dash_null_mood@test.vetlanh")
        resp = await client.get("/api/v1/dashboard", headers=_auth(token))
        assert resp.json()["today_mood"] is None

    async def test_recommended_exercises_is_list(self, client: AsyncClient):
        token = await _register_and_login(client, "dash_recs_type@test.vetlanh")
        resp = await client.get("/api/v1/dashboard", headers=_auth(token))
        assert isinstance(resp.json()["recommended_exercises"], list)

    async def test_recommended_exercises_at_most_three(self, client: AsyncClient):
        token = await _register_and_login(client, "dash_recs_len@test.vetlanh")
        resp = await client.get("/api/v1/dashboard", headers=_auth(token))
        assert len(resp.json()["recommended_exercises"]) <= 3

    async def test_sparkline_contains_today(self, client: AsyncClient):
        token = await _register_and_login(client, "dash_spark_today@test.vetlanh")
        resp = await client.get("/api/v1/dashboard", headers=_auth(token))
        today_str = datetime.now(tz=timezone.utc).date().isoformat()
        dates = [item["date"] for item in resp.json()["mood_sparkline"]]
        assert today_str in dates

    async def test_sparkline_ordered_oldest_to_newest(self, client: AsyncClient):
        token = await _register_and_login(client, "dash_spark_order@test.vetlanh")
        resp = await client.get("/api/v1/dashboard", headers=_auth(token))
        dates = [item["date"] for item in resp.json()["mood_sparkline"]]
        assert dates == sorted(dates)

    async def test_checked_in_today_true_after_mood_checkin(self, client: AsyncClient):
        token = await _register_and_login(client, "dash_ci_true@test.vetlanh")
        headers = _auth(token)
        today_str = datetime.now(tz=timezone.utc).date().isoformat()
        await client.post(
            "/api/v1/mood/entries",
            json={"mood": 3, "date": today_str, "note": "feeling ok"},
            headers=headers,
        )
        resp = await client.get("/api/v1/dashboard", headers=headers)
        assert resp.json()["checked_in_today"] is True

    async def test_today_mood_present_after_checkin(self, client: AsyncClient):
        token = await _register_and_login(client, "dash_mood_present@test.vetlanh")
        headers = _auth(token)
        today_str = datetime.now(tz=timezone.utc).date().isoformat()
        await client.post(
            "/api/v1/mood/entries",
            json={"mood": 4, "date": today_str},
            headers=headers,
        )
        resp = await client.get("/api/v1/dashboard", headers=headers)
        today_mood = resp.json()["today_mood"]
        assert today_mood is not None
        assert today_mood["mood"] == 4

    async def test_streak_one_after_today_checkin(self, client: AsyncClient):
        token = await _register_and_login(client, "dash_streak1@test.vetlanh")
        headers = _auth(token)
        today_str = datetime.now(tz=timezone.utc).date().isoformat()
        await client.post(
            "/api/v1/mood/entries",
            json={"mood": 2, "date": today_str},
            headers=headers,
        )
        resp = await client.get("/api/v1/dashboard", headers=headers)
        assert resp.json()["streak_days"] >= 1

    async def test_sparkline_shows_todays_mood(self, client: AsyncClient):
        token = await _register_and_login(client, "dash_spark_todaymood@test.vetlanh")
        headers = _auth(token)
        today_str = datetime.now(tz=timezone.utc).date().isoformat()
        await client.post("/api/v1/mood/entries", json={"mood": 5, "date": today_str}, headers=headers)
        resp = await client.get("/api/v1/dashboard", headers=headers)
        today_str = datetime.now(tz=timezone.utc).date().isoformat()
        sparkline = resp.json()["mood_sparkline"]
        today_spark = next(s for s in sparkline if s["date"] == today_str)
        assert today_spark["mood"] == 5

    async def test_sparkline_each_item_has_date_and_mood(self, client: AsyncClient):
        token = await _register_and_login(client, "dash_spark_shape@test.vetlanh")
        resp = await client.get("/api/v1/dashboard", headers=_auth(token))
        for item in resp.json()["mood_sparkline"]:
            assert "date" in item
            assert "mood" in item
