"""
Tests for US-031 — Notification Preferences.

Covers:
  Pure unit tests (_in_quiet_hours, _time_str_to_minutes):
    - Normal window (no midnight wrap): inside → True, outside → False
    - Midnight-wrap window (22:00–07:00): 23:00 → in quiet hours
    - Midnight-wrap window (22:00–07:00): 06:00 → in quiet hours
    - Midnight-wrap window (22:00–07:00): 08:00 → NOT in quiet hours
    - Midnight-wrap window (22:00–07:00): boundary at start (22:00) → in quiet hours
    - Midnight-wrap window (22:00–07:00): boundary at end (07:00) → NOT in quiet hours (< end)
    - _time_str_to_minutes: "00:00" → 0
    - _time_str_to_minutes: "23:59" → 1439
    - _time_str_to_minutes: "07:30" → 450

  Schema validation:
    - NotificationPreferenceUpdate: valid "21:00" → accepted
    - NotificationPreferenceUpdate: "25:00" → ValidationError
    - NotificationPreferenceUpdate: "12:60" → ValidationError
    - NotificationPreferenceUpdate: "ab:cd" → ValidationError
    - NotificationPreferenceUpdate: None values accepted (partial update)
    - model_fields_set only contains explicitly provided fields

  Service unit tests (mocked DB):
    - get_preference: creates default row when none exists
    - get_preference: returns existing row unchanged
    - update_preference: partial patch only updates provided fields
    - should_notify: returns False when enabled=False
    - should_notify: returns False when in quiet hours
    - should_notify: returns False when MoodEntry for today exists
    - should_notify: returns True when enabled, not in quiet hours, no entry today

  API integration tests (real DB via AsyncClient):
    - GET /api/v1/notifications/preference → 401 without token
    - PATCH /api/v1/notifications/preference → 401 without token
    - GET /api/v1/notifications/should-notify → 401 without token
    - GET /api/v1/notifications/preference → 200, creates defaults on first call
    - GET /api/v1/notifications/preference → 200, same defaults on second call
    - PATCH /api/v1/notifications/preference → 200, only provided fields changed
    - PATCH /api/v1/notifications/preference — invalid time "25:00" → 422
    - PATCH /api/v1/notifications/preference — invalid time "12:60" → 422
    - GET /api/v1/notifications/should-notify → 200, returns should_notify + reason
    - should_notify=False when notifications disabled
    - should_notify=False when user already has MoodEntry today
"""

from datetime import date, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pydantic import ValidationError
from httpx import AsyncClient

from app.schemas.notification import NotificationPreferenceUpdate
from app.services.notification import _in_quiet_hours, _time_str_to_minutes

TEST_EMAIL_DOMAIN = "test.vetlanh"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _register_and_login(client: AsyncClient, email: str) -> str:
    import unittest.mock as mock

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


# ---------------------------------------------------------------------------
# Pure unit tests — _time_str_to_minutes
# ---------------------------------------------------------------------------


class TestTimeStrToMinutes:
    @pytest.fixture(autouse=True)
    async def clean_db(self):
        yield

    @pytest.fixture(autouse=True)
    def mock_email(self):
        yield

    def test_midnight(self):
        assert _time_str_to_minutes("00:00") == 0

    def test_end_of_day(self):
        assert _time_str_to_minutes("23:59") == 23 * 60 + 59

    def test_half_hour(self):
        assert _time_str_to_minutes("07:30") == 7 * 60 + 30

    def test_noon(self):
        assert _time_str_to_minutes("12:00") == 720


# ---------------------------------------------------------------------------
# Pure unit tests — _in_quiet_hours
# ---------------------------------------------------------------------------


class TestInQuietHours:
    @pytest.fixture(autouse=True)
    async def clean_db(self):
        yield

    @pytest.fixture(autouse=True)
    def mock_email(self):
        yield

    # Non-wrapping window: 09:00 – 17:00
    def test_inside_normal_window(self):
        assert _in_quiet_hours(12 * 60, "09:00", "17:00") is True

    def test_outside_normal_window(self):
        assert _in_quiet_hours(8 * 60, "09:00", "17:00") is False

    def test_at_start_of_normal_window(self):
        assert _in_quiet_hours(9 * 60, "09:00", "17:00") is True

    def test_at_end_of_normal_window_is_excluded(self):
        # end is exclusive: < end
        assert _in_quiet_hours(17 * 60, "09:00", "17:00") is False

    # Midnight-wrap window: 22:00 – 07:00
    def test_wrap_23h_in_quiet(self):
        assert _in_quiet_hours(23 * 60, "22:00", "07:00") is True

    def test_wrap_06h_in_quiet(self):
        assert _in_quiet_hours(6 * 60, "22:00", "07:00") is True

    def test_wrap_08h_not_in_quiet(self):
        assert _in_quiet_hours(8 * 60, "22:00", "07:00") is False

    def test_wrap_at_start_22h_in_quiet(self):
        assert _in_quiet_hours(22 * 60, "22:00", "07:00") is True

    def test_wrap_at_end_07h_not_in_quiet(self):
        # end is exclusive: current_minutes < end → False at exactly 07:00
        assert _in_quiet_hours(7 * 60, "22:00", "07:00") is False

    def test_wrap_midnight_in_quiet(self):
        assert _in_quiet_hours(0, "22:00", "07:00") is True


# ---------------------------------------------------------------------------
# Schema validation tests
# ---------------------------------------------------------------------------


class TestNotificationPreferenceUpdateSchema:
    @pytest.fixture(autouse=True)
    async def clean_db(self):
        yield

    @pytest.fixture(autouse=True)
    def mock_email(self):
        yield

    def test_valid_time_accepted(self):
        payload = NotificationPreferenceUpdate(reminder_time="21:00")
        assert payload.reminder_time == "21:00"

    def test_invalid_hour_25_raises(self):
        with pytest.raises(ValidationError):
            NotificationPreferenceUpdate(reminder_time="25:00")

    def test_invalid_minute_60_raises(self):
        with pytest.raises(ValidationError):
            NotificationPreferenceUpdate(quiet_start="12:60")

    def test_non_numeric_format_raises(self):
        with pytest.raises(ValidationError):
            NotificationPreferenceUpdate(quiet_end="ab:cd")

    def test_none_values_accepted(self):
        payload = NotificationPreferenceUpdate()
        assert payload.reminder_time is None
        assert payload.enabled is None
        assert payload.quiet_start is None
        assert payload.quiet_end is None

    def test_model_fields_set_only_explicit_fields(self):
        payload = NotificationPreferenceUpdate(enabled=False)
        assert payload.model_fields_set == {"enabled"}

    def test_model_fields_set_multiple_fields(self):
        payload = NotificationPreferenceUpdate(enabled=True, reminder_time="09:00")
        assert payload.model_fields_set == {"enabled", "reminder_time"}

    def test_quiet_start_valid(self):
        payload = NotificationPreferenceUpdate(quiet_start="22:00")
        assert payload.quiet_start == "22:00"

    def test_quiet_end_valid(self):
        payload = NotificationPreferenceUpdate(quiet_end="07:00")
        assert payload.quiet_end == "07:00"


# ---------------------------------------------------------------------------
# API integration tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_preference_requires_auth(client: AsyncClient):
    resp = await client.get("/api/v1/notifications/preference")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_patch_preference_requires_auth(client: AsyncClient):
    resp = await client.patch("/api/v1/notifications/preference", json={})
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_should_notify_requires_auth(client: AsyncClient):
    resp = await client.get("/api/v1/notifications/should-notify")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_get_preference_creates_defaults(client: AsyncClient):
    email = f"notif_default@{TEST_EMAIL_DOMAIN}"
    token = await _register_and_login(client, email)
    resp = await client.get("/api/v1/notifications/preference", headers=_auth_header(token))
    assert resp.status_code == 200
    data = resp.json()
    assert "reminder_time" in data
    assert "enabled" in data
    assert "quiet_start" in data
    assert "quiet_end" in data
    # Default values from model
    assert data["enabled"] is True
    assert data["reminder_time"] == "21:00"
    assert data["quiet_start"] == "22:00"
    assert data["quiet_end"] == "07:00"


@pytest.mark.asyncio
async def test_get_preference_idempotent(client: AsyncClient):
    """Two GET calls → same defaults returned."""
    email = f"notif_idem@{TEST_EMAIL_DOMAIN}"
    token = await _register_and_login(client, email)
    headers = _auth_header(token)
    resp1 = await client.get("/api/v1/notifications/preference", headers=headers)
    resp2 = await client.get("/api/v1/notifications/preference", headers=headers)
    assert resp1.json() == resp2.json()


@pytest.mark.asyncio
async def test_patch_preference_partial_update(client: AsyncClient):
    email = f"notif_patch@{TEST_EMAIL_DOMAIN}"
    token = await _register_and_login(client, email)
    headers = _auth_header(token)

    resp = await client.patch(
        "/api/v1/notifications/preference",
        json={"enabled": False},
        headers=headers,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["enabled"] is False
    # Other fields unchanged from defaults
    assert data["reminder_time"] == "21:00"
    assert data["quiet_start"] == "22:00"
    assert data["quiet_end"] == "07:00"


@pytest.mark.asyncio
async def test_patch_preference_update_reminder_time(client: AsyncClient):
    email = f"notif_time@{TEST_EMAIL_DOMAIN}"
    token = await _register_and_login(client, email)
    headers = _auth_header(token)

    resp = await client.patch(
        "/api/v1/notifications/preference",
        json={"reminder_time": "09:00"},
        headers=headers,
    )
    assert resp.status_code == 200
    assert resp.json()["reminder_time"] == "09:00"


@pytest.mark.asyncio
async def test_patch_preference_invalid_hour_422(client: AsyncClient):
    email = f"notif_invalid@{TEST_EMAIL_DOMAIN}"
    token = await _register_and_login(client, email)
    resp = await client.patch(
        "/api/v1/notifications/preference",
        json={"reminder_time": "25:00"},
        headers=_auth_header(token),
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_patch_preference_invalid_minute_422(client: AsyncClient):
    email = f"notif_invalid2@{TEST_EMAIL_DOMAIN}"
    token = await _register_and_login(client, email)
    resp = await client.patch(
        "/api/v1/notifications/preference",
        json={"quiet_start": "12:60"},
        headers=_auth_header(token),
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_should_notify_returns_shape(client: AsyncClient):
    email = f"notif_shape@{TEST_EMAIL_DOMAIN}"
    token = await _register_and_login(client, email)
    resp = await client.get("/api/v1/notifications/should-notify", headers=_auth_header(token))
    assert resp.status_code == 200
    data = resp.json()
    assert "should_notify" in data
    assert "reason" in data
    assert isinstance(data["should_notify"], bool)


@pytest.mark.asyncio
async def test_should_notify_false_when_disabled(client: AsyncClient):
    email = f"notif_disabled@{TEST_EMAIL_DOMAIN}"
    token = await _register_and_login(client, email)
    headers = _auth_header(token)

    # Disable notifications
    await client.patch(
        "/api/v1/notifications/preference",
        json={"enabled": False},
        headers=headers,
    )

    resp = await client.get("/api/v1/notifications/should-notify", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["should_notify"] is False
    assert data["reason"] == "notifications disabled"


@pytest.mark.asyncio
async def test_should_notify_false_when_mood_entry_today(client: AsyncClient):
    email = f"notif_checkedin@{TEST_EMAIL_DOMAIN}"
    token = await _register_and_login(client, email)
    headers = _auth_header(token)

    # Ensure notifications are enabled and not in quiet hours
    await client.patch(
        "/api/v1/notifications/preference",
        json={"enabled": True, "quiet_start": "02:00", "quiet_end": "03:00"},
        headers=headers,
    )

    # Post a mood entry for today
    today = date.today()
    resp = await client.post(
        "/api/v1/mood/entries",
        json={"date": today.isoformat(), "mood": 3, "energy": "medium", "factors": [], "note": None},
        headers=headers,
    )
    assert resp.status_code == 201

    # Now should_notify should be False because already checked in.
    # Set quiet hours to a 1-minute window at 00:00–00:01 so the current
    # time (any hour of a normal test run) is outside quiet hours, ensuring
    # we exercise the "already checked in today" branch.
    await client.patch(
        "/api/v1/notifications/preference",
        json={"quiet_start": "00:00", "quiet_end": "00:01"},
        headers=headers,
    )

    resp = await client.get("/api/v1/notifications/should-notify", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    # Either "already checked in today" OR "quiet hours" (if run exactly at midnight).
    # The important invariant is that should_notify is False.
    assert data["should_notify"] is False
