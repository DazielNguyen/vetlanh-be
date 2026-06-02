"""
Tests for US-032: Daily Exercise Reminder.

Covers:
  - GET /notifications/exercise-reminder returns should_notify=true when no exercise logged today
  - Returns should_notify=false after logging an exercise today
  - Returns should_notify=false when exercise_enabled=false
  - Returns should_notify=false during quiet hours (mocked time)
  - Returns should_notify=false before reminder time (mocked time)
  - PATCH /notifications/preference saves exercise_enabled and exercise_reminder_time
  - PATCH with invalid exercise_reminder_time ("25:00") returns 422
  - Auth required: 401 without token
"""

import unittest.mock as mock
from datetime import datetime, timezone, timedelta
from unittest.mock import patch

import pytest
from httpx import AsyncClient

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_VN_TZ = timezone(timedelta(hours=7))
_MOCK_TARGET = "app.services.notification._now_vn"


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
    assert resp.status_code == 200
    return resp.json()["access_token"]


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _midday_vn() -> datetime:
    """Fixed VN-timezone datetime at 12:00 — after 08:00 default reminder, outside quiet hours."""
    return datetime(2026, 6, 2, 12, 0, 0, tzinfo=_VN_TZ)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestExerciseReminderAuth:
    async def test_no_token_returns_401(self, client: AsyncClient):
        resp = await client.get("/api/v1/notifications/exercise-reminder")
        assert resp.status_code == 401


class TestExerciseReminderEndpoint:
    async def test_returns_200(self, client: AsyncClient):
        token = await _register_and_login(client, "exrem_200@test.vetlanh")
        with patch(_MOCK_TARGET, return_value=_midday_vn()):
            resp = await client.get(
                "/api/v1/notifications/exercise-reminder", headers=_auth(token)
            )
        assert resp.status_code == 200

    async def test_should_notify_true_when_no_exercise_logged(self, client: AsyncClient):
        token = await _register_and_login(client, "exrem_notlogged@test.vetlanh")
        with patch(_MOCK_TARGET, return_value=_midday_vn()):
            resp = await client.get(
                "/api/v1/notifications/exercise-reminder", headers=_auth(token)
            )
        data = resp.json()
        assert data["should_notify"] is True
        assert data["reason"] == "ok"

    async def test_should_notify_false_after_exercise_logged(self, client: AsyncClient):
        token = await _register_and_login(client, "exrem_logged@test.vetlanh")
        headers = _auth(token)

        await client.post(
            "/api/v1/exercises/logs",
            json={"exercise_slug": "box-breathing", "duration_seconds": 300},
            headers=headers,
        )

        with patch(_MOCK_TARGET, return_value=_midday_vn()):
            resp = await client.get(
                "/api/v1/notifications/exercise-reminder", headers=headers
            )
        data = resp.json()
        assert data["should_notify"] is False
        assert data["reason"] == "already exercised today"

    async def test_should_notify_false_when_exercise_disabled(self, client: AsyncClient):
        token = await _register_and_login(client, "exrem_disabled@test.vetlanh")
        headers = _auth(token)

        await client.patch(
            "/api/v1/notifications/preference",
            json={"exercise_enabled": False},
            headers=headers,
        )

        with patch(_MOCK_TARGET, return_value=_midday_vn()):
            resp = await client.get(
                "/api/v1/notifications/exercise-reminder", headers=headers
            )
        data = resp.json()
        assert data["should_notify"] is False
        assert data["reason"] == "exercise notifications disabled"

    async def test_should_notify_false_during_quiet_hours(self, client: AsyncClient):
        token = await _register_and_login(client, "exrem_quiet@test.vetlanh")
        headers = _auth(token)

        await client.patch(
            "/api/v1/notifications/preference",
            json={"quiet_start": "23:00", "quiet_end": "06:00"},
            headers=headers,
        )

        quiet_time = datetime(2026, 6, 2, 23, 30, 0, tzinfo=_VN_TZ)
        with patch(_MOCK_TARGET, return_value=quiet_time):
            resp = await client.get(
                "/api/v1/notifications/exercise-reminder", headers=headers
            )
        data = resp.json()
        assert data["should_notify"] is False
        assert data["reason"] == "quiet hours"

    async def test_should_notify_false_before_reminder_time(self, client: AsyncClient):
        token = await _register_and_login(client, "exrem_early@test.vetlanh")
        headers = _auth(token)

        await client.patch(
            "/api/v1/notifications/preference",
            json={"exercise_reminder_time": "14:00"},
            headers=headers,
        )

        early = datetime(2026, 6, 2, 9, 0, 0, tzinfo=_VN_TZ)
        with patch(_MOCK_TARGET, return_value=early):
            resp = await client.get(
                "/api/v1/notifications/exercise-reminder", headers=headers
            )
        data = resp.json()
        assert data["should_notify"] is False
        assert data["reason"] == "not yet reminder time"

    async def test_response_has_should_notify_and_reason_fields(self, client: AsyncClient):
        token = await _register_and_login(client, "exrem_shape@test.vetlanh")
        with patch(_MOCK_TARGET, return_value=_midday_vn()):
            resp = await client.get(
                "/api/v1/notifications/exercise-reminder", headers=_auth(token)
            )
        data = resp.json()
        assert "should_notify" in data
        assert "reason" in data


class TestExerciseReminderPreference:
    async def test_patch_exercise_enabled_false(self, client: AsyncClient):
        token = await _register_and_login(client, "exrem_pref_dis@test.vetlanh")
        resp = await client.patch(
            "/api/v1/notifications/preference",
            json={"exercise_enabled": False},
            headers=_auth(token),
        )
        assert resp.status_code == 200
        assert resp.json()["exercise_enabled"] is False

    async def test_patch_exercise_enabled_true(self, client: AsyncClient):
        token = await _register_and_login(client, "exrem_pref_en@test.vetlanh")
        await client.patch(
            "/api/v1/notifications/preference",
            json={"exercise_enabled": False},
            headers=_auth(token),
        )
        resp = await client.patch(
            "/api/v1/notifications/preference",
            json={"exercise_enabled": True},
            headers=_auth(token),
        )
        assert resp.json()["exercise_enabled"] is True

    async def test_patch_exercise_reminder_time(self, client: AsyncClient):
        token = await _register_and_login(client, "exrem_pref_time@test.vetlanh")
        resp = await client.patch(
            "/api/v1/notifications/preference",
            json={"exercise_reminder_time": "10:00"},
            headers=_auth(token),
        )
        assert resp.status_code == 200
        assert resp.json()["exercise_reminder_time"] == "10:00"

    async def test_patch_invalid_exercise_reminder_time_returns_422(self, client: AsyncClient):
        token = await _register_and_login(client, "exrem_pref_bad@test.vetlanh")
        resp = await client.patch(
            "/api/v1/notifications/preference",
            json={"exercise_reminder_time": "25:00"},
            headers=_auth(token),
        )
        assert resp.status_code == 422

    async def test_get_preference_includes_exercise_fields(self, client: AsyncClient):
        token = await _register_and_login(client, "exrem_pref_get@test.vetlanh")
        resp = await client.get(
            "/api/v1/notifications/preference", headers=_auth(token)
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "exercise_enabled" in data
        assert "exercise_reminder_time" in data

    async def test_preference_defaults_exercise_enabled_true(self, client: AsyncClient):
        token = await _register_and_login(client, "exrem_pref_def@test.vetlanh")
        resp = await client.get(
            "/api/v1/notifications/preference", headers=_auth(token)
        )
        assert resp.json()["exercise_enabled"] is True

    async def test_preference_defaults_exercise_reminder_time(self, client: AsyncClient):
        token = await _register_and_login(client, "exrem_pref_defrt@test.vetlanh")
        resp = await client.get(
            "/api/v1/notifications/preference", headers=_auth(token)
        )
        assert resp.json()["exercise_reminder_time"] == "08:00"
