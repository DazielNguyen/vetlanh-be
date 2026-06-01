"""
Tests for US-014 Mood Insights.

Covers:
  Pure function unit tests (no DB — mock MoodEntry objects):
    _day_of_week_insight:
      - Returns None when no weekday has >= _MIN_SAMPLE entries
      - Returns None when best weekday avg < overall_avg + _INSIGHT_THRESHOLD
      - Returns InsightItem when one weekday clearly dominates
      - Text contains correct Vietnamese day name from _VN_DAYS
      - delta field matches computed value
      - Handles all 7 weekdays correctly

    _factor_correlation_insight:
      - Returns None when no factors present
      - Returns None when best factor delta < _INSIGHT_THRESHOLD
      - Returns None when factor has < _MIN_SAMPLE occurrences
      - Returns InsightItem with correct factor name and delta
      - Selects the factor with highest delta among multiple candidates

  Service unit tests (get_insights with mocked list_entries):
    - Returns has_enough_data=False when total < 7
    - Returns has_enough_data=True with overall_average insight when >= 7 entries
    - overall_average text includes entry count and rounded avg
    - Calls list_entries with limit=500

  API integration tests (real DB):
    - GET /mood/insights → 401 without auth
    - GET /mood/insights → 200 with has_enough_data=false for 0 entries
    - GET /mood/insights → 200 with has_enough_data=false with 6 entries
    - GET /mood/insights → 200 with has_enough_data=true with 7+ entries
    - Response always contains total_entries, has_enough_data, insights fields
    - User A's entries don't affect User B's insights
"""

from datetime import date
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import AsyncClient

from app.schemas.mood import InsightItem, InsightsResponse
from app.services.insights import (
    _VN_DAYS,
    _day_of_week_insight,
    _factor_correlation_insight,
    get_insights,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

TEST_EMAIL_DOMAIN = "test.vetlanh"
# 2026-05-04 is a Monday (weekday() == 0)
_MONDAY = date(2026, 5, 4)


def _make_entry(mood: int, weekday_offset: int = 0, factors: list[str] = None):
    """Create a mock MoodEntry-like object.

    weekday_offset shifts date from a Monday (2026-05-04):
      0 → Monday, 1 → Tuesday, ..., 6 → Sunday
    """
    m = MagicMock()
    m.mood = mood
    m.date = date(2026, 5, 4 + weekday_offset)
    m.factors = factors or []
    return m


def _make_list_db(entries: list) -> AsyncMock:
    """Build an AsyncSession-like mock whose execute returns entries via scalars().all()."""
    scalars_mock = MagicMock()
    scalars_mock.all.return_value = entries

    result_mock = MagicMock()
    result_mock.scalars.return_value = scalars_mock

    db = AsyncMock()
    db.execute = AsyncMock(return_value=result_mock)
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


def _mood_body(date_str: str = "2026-05-04", mood: int = 3, factors: list[str] = None) -> dict:
    body = {
        "date": date_str,
        "mood": mood,
        "energy": "medium",
        "factors": factors or [],
        "note": None,
    }
    return body


# ---------------------------------------------------------------------------
# Pure function unit tests — _day_of_week_insight
# ---------------------------------------------------------------------------


class TestDayOfWeekInsight:
    """Unit tests for _day_of_week_insight. No DB required."""

    @pytest.fixture(autouse=True)
    async def clean_db(self):  # noqa: F811  (overrides conftest autouse)
        yield

    @pytest.fixture(autouse=True)
    def mock_email(self):  # noqa: F811
        yield

    def test_returns_none_when_no_entries(self):
        result = _day_of_week_insight([], overall_avg=3.0)
        assert result is None

    def test_returns_none_when_each_weekday_has_only_one_entry(self):
        """_MIN_SAMPLE == 2, so a single entry per weekday is not enough."""
        entries = [
            _make_entry(mood=5, weekday_offset=0),  # Monday
            _make_entry(mood=5, weekday_offset=1),  # Tuesday
        ]
        result = _day_of_week_insight(entries, overall_avg=3.0)
        assert result is None

    def test_returns_none_when_best_avg_not_above_threshold(self):
        """Best weekday avg must exceed overall_avg + 0.3."""
        # Monday has 2 entries with avg=3.2, overall_avg=3.0 → delta=0.2 < 0.3
        entries = [
            _make_entry(mood=3, weekday_offset=0),
            _make_entry(mood=3, weekday_offset=0),  # avg = 3.0 Monday
            _make_entry(mood=4, weekday_offset=1),  # Tuesday single entry
        ]
        # overrall_avg=3.2 → Monday avg 3.0 < 3.2 + 0.3
        result = _day_of_week_insight(entries, overall_avg=3.2)
        assert result is None

    def test_returns_insight_when_delta_above_threshold(self):
        """Monday avg=3.5, overall=3.0, delta=0.5 — well above 0.3 threshold → insight returned."""
        entries = [
            _make_entry(mood=3, weekday_offset=0),
            _make_entry(mood=4, weekday_offset=0),  # Monday avg = 3.5
        ]
        overall_avg = 3.0
        result = _day_of_week_insight(entries, overall_avg=overall_avg)
        # 3.5 >= 3.0 + 0.3 → should return insight
        assert result is not None

    def test_returns_insight_item_when_one_weekday_dominates(self):
        """When Monday has clearly higher avg, InsightItem should be returned."""
        entries = [
            _make_entry(mood=5, weekday_offset=0),
            _make_entry(mood=5, weekday_offset=0),  # Monday avg=5
            _make_entry(mood=2, weekday_offset=1),
            _make_entry(mood=2, weekday_offset=1),  # Tuesday avg=2
        ]
        result = _day_of_week_insight(entries, overall_avg=3.0)
        assert result is not None
        assert isinstance(result, InsightItem)

    def test_insight_type_is_day_of_week(self):
        entries = [
            _make_entry(mood=5, weekday_offset=0),
            _make_entry(mood=5, weekday_offset=0),
        ]
        result = _day_of_week_insight(entries, overall_avg=3.0)
        assert result is not None
        assert result.type == "day_of_week"

    def test_text_contains_correct_vn_day_name_monday(self):
        """Monday (offset=0) should produce text with 'thứ Hai'."""
        entries = [
            _make_entry(mood=5, weekday_offset=0),
            _make_entry(mood=5, weekday_offset=0),
        ]
        result = _day_of_week_insight(entries, overall_avg=2.0)
        assert result is not None
        assert _VN_DAYS[0] in result.text  # "thứ Hai"

    def test_text_contains_correct_vn_day_name_tuesday(self):
        entries = [
            _make_entry(mood=5, weekday_offset=1),
            _make_entry(mood=5, weekday_offset=1),
        ]
        result = _day_of_week_insight(entries, overall_avg=2.0)
        assert result is not None
        assert _VN_DAYS[1] in result.text  # "thứ Ba"

    def test_text_contains_correct_vn_day_name_wednesday(self):
        entries = [
            _make_entry(mood=5, weekday_offset=2),
            _make_entry(mood=5, weekday_offset=2),
        ]
        result = _day_of_week_insight(entries, overall_avg=2.0)
        assert result is not None
        assert _VN_DAYS[2] in result.text  # "thứ Tư"

    def test_text_contains_correct_vn_day_name_thursday(self):
        entries = [
            _make_entry(mood=5, weekday_offset=3),
            _make_entry(mood=5, weekday_offset=3),
        ]
        result = _day_of_week_insight(entries, overall_avg=2.0)
        assert result is not None
        assert _VN_DAYS[3] in result.text  # "thứ Năm"

    def test_text_contains_correct_vn_day_name_friday(self):
        entries = [
            _make_entry(mood=5, weekday_offset=4),
            _make_entry(mood=5, weekday_offset=4),
        ]
        result = _day_of_week_insight(entries, overall_avg=2.0)
        assert result is not None
        assert _VN_DAYS[4] in result.text  # "thứ Sáu"

    def test_text_contains_correct_vn_day_name_saturday(self):
        entries = [
            _make_entry(mood=5, weekday_offset=5),
            _make_entry(mood=5, weekday_offset=5),
        ]
        result = _day_of_week_insight(entries, overall_avg=2.0)
        assert result is not None
        assert _VN_DAYS[5] in result.text  # "thứ Bảy"

    def test_text_contains_correct_vn_day_name_sunday(self):
        entries = [
            _make_entry(mood=5, weekday_offset=6),
            _make_entry(mood=5, weekday_offset=6),
        ]
        result = _day_of_week_insight(entries, overall_avg=2.0)
        assert result is not None
        assert _VN_DAYS[6] in result.text  # "Chủ nhật"

    def test_delta_field_matches_computed_value(self):
        """Delta should equal round(best_avg - overall_avg, 1)."""
        entries = [
            _make_entry(mood=5, weekday_offset=0),
            _make_entry(mood=5, weekday_offset=0),  # Monday avg=5.0
        ]
        overall_avg = 3.0
        result = _day_of_week_insight(entries, overall_avg=overall_avg)
        assert result is not None
        expected_delta = round(5.0 - 3.0, 1)  # 2.0
        assert result.delta == expected_delta

    def test_delta_field_is_rounded_to_one_decimal(self):
        """Delta is rounded to 1 decimal place."""
        # avg=4.0, overall=2.67 → delta=1.33 → rounds to 1.3
        entries = [
            _make_entry(mood=4, weekday_offset=0),
            _make_entry(mood=4, weekday_offset=0),
        ]
        result = _day_of_week_insight(entries, overall_avg=2.67)
        assert result is not None
        assert result.delta == round(4.0 - 2.67, 1)

    def test_selects_highest_average_weekday(self):
        """When multiple weekdays qualify, the one with highest avg is chosen."""
        entries = [
            _make_entry(mood=4, weekday_offset=0),
            _make_entry(mood=4, weekday_offset=0),  # Monday avg=4.0
            _make_entry(mood=5, weekday_offset=2),
            _make_entry(mood=5, weekday_offset=2),  # Wednesday avg=5.0 → winner
        ]
        result = _day_of_week_insight(entries, overall_avg=2.0)
        assert result is not None
        assert _VN_DAYS[2] in result.text  # Wednesday should win

    def test_ignores_weekday_with_only_one_entry(self):
        """A weekday that has only 1 entry should not appear in result even if its avg is high."""
        entries = [
            _make_entry(mood=5, weekday_offset=0),  # Monday: 1 entry — ignored
            _make_entry(mood=3, weekday_offset=1),
            _make_entry(mood=3, weekday_offset=1),  # Tuesday: 2 entries, avg=3.0
        ]
        # Monday would have higher avg but has only 1 entry
        result = _day_of_week_insight(entries, overall_avg=2.0)
        assert result is not None
        assert _VN_DAYS[1] in result.text  # Tuesday wins (Monday excluded)


# ---------------------------------------------------------------------------
# Pure function unit tests — _factor_correlation_insight
# ---------------------------------------------------------------------------


class TestFactorCorrelationInsight:
    """Unit tests for _factor_correlation_insight. No DB required."""

    @pytest.fixture(autouse=True)
    async def clean_db(self):  # noqa: F811
        yield

    @pytest.fixture(autouse=True)
    def mock_email(self):  # noqa: F811
        yield

    def test_returns_none_when_all_entries_have_no_factors(self):
        entries = [_make_entry(mood=4, factors=[]) for _ in range(5)]
        result = _factor_correlation_insight(entries, overall_avg=3.0)
        assert result is None

    def test_returns_none_when_empty_entries(self):
        result = _factor_correlation_insight([], overall_avg=3.0)
        assert result is None

    def test_returns_none_when_factor_has_only_one_occurrence(self):
        """_MIN_SAMPLE == 2, single occurrence not counted."""
        entries = [_make_entry(mood=5, factors=["exercise"])]
        result = _factor_correlation_insight(entries, overall_avg=3.0)
        assert result is None

    def test_returns_none_when_factor_delta_below_threshold(self):
        """Factor avg must exceed overall_avg by > _INSIGHT_THRESHOLD=0.3."""
        entries = [
            _make_entry(mood=3, factors=["work"]),
            _make_entry(mood=3, factors=["work"]),  # work avg=3.0
        ]
        # delta = 3.0 - 3.0 = 0.0 < 0.3
        result = _factor_correlation_insight(entries, overall_avg=3.0)
        assert result is None

    def test_returns_none_when_delta_exactly_equals_threshold(self):
        """_factor_correlation_insight uses > _INSIGHT_THRESHOLD (strict), so exactly 0.3 returns None."""
        entries = [
            _make_entry(mood=3, factors=["work"]),
            _make_entry(mood=4, factors=["work"]),  # work avg=3.5
        ]
        # delta = 3.5 - 3.2 = 0.3 — NOT strictly greater than 0.3 → None
        result = _factor_correlation_insight(entries, overall_avg=3.2)
        assert result is None

    def test_returns_insight_when_factor_clearly_correlates(self):
        entries = [
            _make_entry(mood=5, factors=["exercise"]),
            _make_entry(mood=5, factors=["exercise"]),  # exercise avg=5.0
        ]
        result = _factor_correlation_insight(entries, overall_avg=2.0)
        assert result is not None
        assert isinstance(result, InsightItem)

    def test_insight_type_is_factor_correlation(self):
        entries = [
            _make_entry(mood=5, factors=["exercise"]),
            _make_entry(mood=5, factors=["exercise"]),
        ]
        result = _factor_correlation_insight(entries, overall_avg=2.0)
        assert result is not None
        assert result.type == "factor_correlation"

    def test_text_contains_factor_name(self):
        entries = [
            _make_entry(mood=5, factors=["sleep"]),
            _make_entry(mood=5, factors=["sleep"]),
        ]
        result = _factor_correlation_insight(entries, overall_avg=2.0)
        assert result is not None
        assert "sleep" in result.text

    def test_delta_field_matches_computed_value(self):
        entries = [
            _make_entry(mood=5, factors=["music"]),
            _make_entry(mood=5, factors=["music"]),  # avg=5.0
        ]
        overall_avg = 3.0
        result = _factor_correlation_insight(entries, overall_avg=overall_avg)
        assert result is not None
        expected_delta = round(5.0 - 3.0, 1)  # 2.0
        assert result.delta == expected_delta

    def test_selects_factor_with_highest_delta(self):
        """When multiple factors qualify, the one with highest avg - overall_avg is chosen."""
        entries = [
            _make_entry(mood=4, factors=["work"]),
            _make_entry(mood=4, factors=["work"]),   # work avg=4.0, delta=1.0
            _make_entry(mood=5, factors=["music"]),
            _make_entry(mood=5, factors=["music"]),  # music avg=5.0, delta=2.0 → winner
        ]
        result = _factor_correlation_insight(entries, overall_avg=3.0)
        assert result is not None
        assert "music" in result.text

    def test_handles_entry_with_multiple_factors(self):
        """An entry with multiple factors contributes its mood to each factor's list."""
        entries = [
            _make_entry(mood=5, factors=["sleep", "exercise"]),
            _make_entry(mood=5, factors=["sleep", "exercise"]),
        ]
        result = _factor_correlation_insight(entries, overall_avg=2.0)
        assert result is not None
        # Either sleep or exercise should appear
        assert "sleep" in result.text or "exercise" in result.text

    def test_factor_with_negative_delta_not_selected(self):
        """Factors where delta is negative (worse than avg) should not be chosen."""
        entries = [
            _make_entry(mood=1, factors=["stress"]),
            _make_entry(mood=1, factors=["stress"]),  # stress avg=1.0, delta=-2.0
        ]
        result = _factor_correlation_insight(entries, overall_avg=3.0)
        assert result is None


# ---------------------------------------------------------------------------
# Service unit tests — get_insights (mocking list_entries)
# ---------------------------------------------------------------------------


class TestGetInsightsService:
    """Unit tests for get_insights service function."""

    @pytest.fixture(autouse=True)
    async def clean_db(self):  # noqa: F811
        yield

    @pytest.fixture(autouse=True)
    def mock_email(self):  # noqa: F811
        yield

    async def test_returns_has_enough_data_false_when_zero_entries(self):
        db = _make_list_db([])
        with patch("app.services.insights.list_entries", new_callable=AsyncMock, return_value=[]):
            result = await get_insights(db, user_id=1)
        assert result.has_enough_data is False

    async def test_returns_empty_insights_when_not_enough_data(self):
        with patch("app.services.insights.list_entries", new_callable=AsyncMock, return_value=[]):
            db = _make_list_db([])
            result = await get_insights(db, user_id=1)
        assert result.insights == []

    async def test_total_entries_correct_when_zero(self):
        with patch("app.services.insights.list_entries", new_callable=AsyncMock, return_value=[]):
            db = _make_list_db([])
            result = await get_insights(db, user_id=1)
        assert result.total_entries == 0

    async def test_returns_has_enough_data_false_for_six_entries(self):
        """6 entries < _MIN_ENTRIES=7 → has_enough_data=False."""
        entries = [_make_entry(mood=3, weekday_offset=i % 7) for i in range(6)]
        with patch("app.services.insights.list_entries", new_callable=AsyncMock, return_value=entries):
            db = _make_list_db(entries)
            result = await get_insights(db, user_id=1)
        assert result.has_enough_data is False

    async def test_total_entries_correct_for_six_entries(self):
        entries = [_make_entry(mood=3, weekday_offset=i % 7) for i in range(6)]
        with patch("app.services.insights.list_entries", new_callable=AsyncMock, return_value=entries):
            db = _make_list_db(entries)
            result = await get_insights(db, user_id=1)
        assert result.total_entries == 6

    async def test_returns_has_enough_data_true_for_seven_entries(self):
        """7 entries == _MIN_ENTRIES → has_enough_data=True."""
        entries = [_make_entry(mood=3, weekday_offset=i % 7) for i in range(7)]
        with patch("app.services.insights.list_entries", new_callable=AsyncMock, return_value=entries):
            db = _make_list_db(entries)
            result = await get_insights(db, user_id=1)
        assert result.has_enough_data is True

    async def test_overall_average_insight_present_when_enough_data(self):
        entries = [_make_entry(mood=3, weekday_offset=i % 7) for i in range(7)]
        with patch("app.services.insights.list_entries", new_callable=AsyncMock, return_value=entries):
            db = _make_list_db(entries)
            result = await get_insights(db, user_id=1)
        types = [i.type for i in result.insights]
        assert "overall_average" in types

    async def test_overall_average_text_includes_entry_count(self):
        entries = [_make_entry(mood=3, weekday_offset=i % 7) for i in range(7)]
        with patch("app.services.insights.list_entries", new_callable=AsyncMock, return_value=entries):
            db = _make_list_db(entries)
            result = await get_insights(db, user_id=1)
        overall = next(i for i in result.insights if i.type == "overall_average")
        assert "7" in overall.text

    async def test_overall_average_text_includes_rounded_avg(self):
        """Average of 7 entries all with mood=3 → 3.0."""
        entries = [_make_entry(mood=3, weekday_offset=i % 7) for i in range(7)]
        with patch("app.services.insights.list_entries", new_callable=AsyncMock, return_value=entries):
            db = _make_list_db(entries)
            result = await get_insights(db, user_id=1)
        overall = next(i for i in result.insights if i.type == "overall_average")
        assert "3.0" in overall.text

    async def test_list_entries_called_with_limit_500(self):
        """get_insights must call list_entries with limit=500."""
        mock_list_entries = AsyncMock(return_value=[])
        with patch("app.services.insights.list_entries", mock_list_entries):
            db = _make_list_db([])
            await get_insights(db, user_id=42)
        mock_list_entries.assert_called_once()
        _, kwargs = mock_list_entries.call_args
        # Could be positional or keyword; check both
        call_args = mock_list_entries.call_args
        assert call_args[1].get("limit") == 500

    async def test_total_entries_reflects_actual_count(self):
        entries = [_make_entry(mood=4, weekday_offset=i % 7) for i in range(10)]
        with patch("app.services.insights.list_entries", new_callable=AsyncMock, return_value=entries):
            db = _make_list_db(entries)
            result = await get_insights(db, user_id=1)
        assert result.total_entries == 10

    async def test_response_is_insights_response_type(self):
        with patch("app.services.insights.list_entries", new_callable=AsyncMock, return_value=[]):
            db = _make_list_db([])
            result = await get_insights(db, user_id=1)
        assert isinstance(result, InsightsResponse)

    async def test_at_least_one_insight_when_enough_data(self):
        entries = [_make_entry(mood=3, weekday_offset=i % 7) for i in range(7)]
        with patch("app.services.insights.list_entries", new_callable=AsyncMock, return_value=entries):
            db = _make_list_db(entries)
            result = await get_insights(db, user_id=1)
        assert len(result.insights) >= 1


# ---------------------------------------------------------------------------
# API integration tests — GET /mood/insights
# ---------------------------------------------------------------------------


class TestGetMoodInsightsAPI:
    """Integration tests for GET /mood/insights using real DB."""

    async def test_unauthenticated_returns_401(self, client: AsyncClient):
        resp = await client.get("/api/v1/mood/insights")
        assert resp.status_code == 401

    async def test_invalid_token_returns_401(self, client: AsyncClient):
        resp = await client.get(
            "/api/v1/mood/insights",
            headers={"Authorization": "Bearer this.is.not.valid"},
        )
        assert resp.status_code == 401

    async def test_new_user_zero_entries_returns_200(self, client: AsyncClient):
        token = await _register_and_login(client, "insights_zero@test.vetlanh")
        resp = await client.get("/api/v1/mood/insights", headers=_auth_header(token))
        assert resp.status_code == 200

    async def test_new_user_has_enough_data_false(self, client: AsyncClient):
        token = await _register_and_login(client, "insights_nodata@test.vetlanh")
        resp = await client.get("/api/v1/mood/insights", headers=_auth_header(token))
        assert resp.json()["has_enough_data"] is False

    async def test_new_user_insights_list_empty(self, client: AsyncClient):
        token = await _register_and_login(client, "insights_empty@test.vetlanh")
        resp = await client.get("/api/v1/mood/insights", headers=_auth_header(token))
        assert resp.json()["insights"] == []

    async def test_new_user_total_entries_zero(self, client: AsyncClient):
        token = await _register_and_login(client, "insights_total0@test.vetlanh")
        resp = await client.get("/api/v1/mood/insights", headers=_auth_header(token))
        assert resp.json()["total_entries"] == 0

    async def test_six_entries_has_enough_data_false(self, client: AsyncClient):
        """6 entries < 7 minimum → has_enough_data=False."""
        token = await _register_and_login(client, "insights_6entries@test.vetlanh")
        headers = _auth_header(token)

        dates = [
            "2026-05-04", "2026-05-05", "2026-05-06", "2026-05-07",
            "2026-05-08", "2026-05-09",
        ]
        for d in dates:
            await client.post("/api/v1/mood/entries", json=_mood_body(date_str=d, mood=3), headers=headers)

        resp = await client.get("/api/v1/mood/insights", headers=headers)
        assert resp.status_code == 200
        assert resp.json()["has_enough_data"] is False

    async def test_six_entries_total_entries_count(self, client: AsyncClient):
        token = await _register_and_login(client, "insights_6total@test.vetlanh")
        headers = _auth_header(token)

        dates = [
            "2026-05-04", "2026-05-05", "2026-05-06", "2026-05-07",
            "2026-05-08", "2026-05-09",
        ]
        for d in dates:
            await client.post("/api/v1/mood/entries", json=_mood_body(date_str=d, mood=3), headers=headers)

        resp = await client.get("/api/v1/mood/insights", headers=headers)
        assert resp.json()["total_entries"] == 6

    async def test_seven_entries_has_enough_data_true(self, client: AsyncClient):
        """7 entries >= 7 minimum → has_enough_data=True."""
        token = await _register_and_login(client, "insights_7entries@test.vetlanh")
        headers = _auth_header(token)

        dates = [
            "2026-05-04", "2026-05-05", "2026-05-06", "2026-05-07",
            "2026-05-08", "2026-05-09", "2026-05-10",
        ]
        for d in dates:
            await client.post("/api/v1/mood/entries", json=_mood_body(date_str=d, mood=3), headers=headers)

        resp = await client.get("/api/v1/mood/insights", headers=headers)
        assert resp.status_code == 200
        assert resp.json()["has_enough_data"] is True

    async def test_seven_entries_at_least_one_insight(self, client: AsyncClient):
        token = await _register_and_login(client, "insights_7insight@test.vetlanh")
        headers = _auth_header(token)

        dates = [
            "2026-05-04", "2026-05-05", "2026-05-06", "2026-05-07",
            "2026-05-08", "2026-05-09", "2026-05-10",
        ]
        for d in dates:
            await client.post("/api/v1/mood/entries", json=_mood_body(date_str=d, mood=3), headers=headers)

        resp = await client.get("/api/v1/mood/insights", headers=headers)
        assert len(resp.json()["insights"]) >= 1

    async def test_seven_entries_total_entries_count(self, client: AsyncClient):
        token = await _register_and_login(client, "insights_7total@test.vetlanh")
        headers = _auth_header(token)

        dates = [
            "2026-05-04", "2026-05-05", "2026-05-06", "2026-05-07",
            "2026-05-08", "2026-05-09", "2026-05-10",
        ]
        for d in dates:
            await client.post("/api/v1/mood/entries", json=_mood_body(date_str=d, mood=3), headers=headers)

        resp = await client.get("/api/v1/mood/insights", headers=headers)
        assert resp.json()["total_entries"] == 7

    async def test_response_always_contains_required_fields(self, client: AsyncClient):
        token = await _register_and_login(client, "insights_fields@test.vetlanh")
        resp = await client.get("/api/v1/mood/insights", headers=_auth_header(token))
        body = resp.json()
        for field in ("total_entries", "has_enough_data", "insights"):
            assert field in body, f"Missing field: {field}"

    async def test_insights_list_contains_insight_item_fields(self, client: AsyncClient):
        """Each item in insights list should have type, text fields."""
        token = await _register_and_login(client, "insights_itemfields@test.vetlanh")
        headers = _auth_header(token)

        dates = [
            "2026-05-04", "2026-05-05", "2026-05-06", "2026-05-07",
            "2026-05-08", "2026-05-09", "2026-05-10",
        ]
        for d in dates:
            await client.post("/api/v1/mood/entries", json=_mood_body(date_str=d, mood=3), headers=headers)

        resp = await client.get("/api/v1/mood/insights", headers=headers)
        items = resp.json()["insights"]
        assert len(items) >= 1
        for item in items:
            assert "type" in item
            assert "text" in item

    async def test_user_isolation_different_users(self, client: AsyncClient):
        """User A's entries must not appear in User B's insights."""
        token_a = await _register_and_login(client, "insights_usera@test.vetlanh")
        token_b = await _register_and_login(client, "insights_userb@test.vetlanh")

        # User A creates 7 entries
        dates = [
            "2026-05-04", "2026-05-05", "2026-05-06", "2026-05-07",
            "2026-05-08", "2026-05-09", "2026-05-10",
        ]
        for d in dates:
            await client.post(
                "/api/v1/mood/entries",
                json=_mood_body(date_str=d, mood=5),
                headers=_auth_header(token_a),
            )

        # User B has 0 entries → should still return has_enough_data=False
        resp_b = await client.get("/api/v1/mood/insights", headers=_auth_header(token_b))
        assert resp_b.status_code == 200
        assert resp_b.json()["has_enough_data"] is False
        assert resp_b.json()["total_entries"] == 0

    async def test_user_a_insights_independent_of_user_b(self, client: AsyncClient):
        """User A with enough data gets insights even when User B has 0."""
        token_a = await _register_and_login(client, "insights_a_check@test.vetlanh")
        token_b = await _register_and_login(client, "insights_b_check@test.vetlanh")  # noqa: F841

        dates = [
            "2026-05-04", "2026-05-05", "2026-05-06", "2026-05-07",
            "2026-05-08", "2026-05-09", "2026-05-10",
        ]
        for d in dates:
            await client.post(
                "/api/v1/mood/entries",
                json=_mood_body(date_str=d, mood=4),
                headers=_auth_header(token_a),
            )

        resp_a = await client.get("/api/v1/mood/insights", headers=_auth_header(token_a))
        assert resp_a.json()["has_enough_data"] is True

    async def test_overall_average_insight_type_present(self, client: AsyncClient):
        """With 7+ entries, overall_average insight type must be in insights list."""
        token = await _register_and_login(client, "insights_overall@test.vetlanh")
        headers = _auth_header(token)

        dates = [
            "2026-05-04", "2026-05-05", "2026-05-06", "2026-05-07",
            "2026-05-08", "2026-05-09", "2026-05-10",
        ]
        for d in dates:
            await client.post("/api/v1/mood/entries", json=_mood_body(date_str=d, mood=3), headers=headers)

        resp = await client.get("/api/v1/mood/insights", headers=headers)
        types = [i["type"] for i in resp.json()["insights"]]
        assert "overall_average" in types
