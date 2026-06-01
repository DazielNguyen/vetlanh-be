"""
Tests for Epic E2 Assessment Sprint 2 — PHQ-9 History & Reminder (US-013).

Covers:
  Service unit tests (no real DB — AsyncMock):
    - get_phq9_reminder: no assessments → due=True, days_since_last=None, next_due_in_days=0
    - get_phq9_reminder: 0 days ago → due=False, days_since_last=0, next_due_in_days=14
    - get_phq9_reminder: 13 days ago → due=False, days_since_last=13, next_due_in_days=1
    - get_phq9_reminder: 14 days ago → due=True, days_since_last=14, next_due_in_days=0
    - get_phq9_reminder: 20 days ago → due=True, days_since_last=20, next_due_in_days=0
    - get_phq9_history: single assessment → delta=None
    - get_phq9_history: two assessments (12, 8) → newest delta=-4, oldest delta=None
    - get_phq9_history: three assessments (12, 8, 10) → deltas 2, -4, None

  API integration tests (real DB, in-process HTTP via AsyncClient):
    - GET /assessments/phq9/history with no assessments → 200, empty list
    - GET /assessments/phq9/history with 2 assessments → newest first, correct score_delta
    - GET /assessments/phq9/reminder with no assessments → 200, due=true
    - GET /assessments/phq9/reminder after just submitting → due=false
    - GET /assessments/phq9/history without auth → 401
    - GET /assessments/phq9/reminder without auth → 401
    - POST /assessments/phq9 first time → score_delta=null
    - POST /assessments/phq9 second time → score_delta = new_score - old_score
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import AsyncClient

from app.services.assessment import get_phq9_history, get_phq9_reminder


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

TEST_EMAIL_DOMAIN = "test.vetlanh"

# Answers that sum to a known score
_ANSWERS_SCORE_12 = [2, 2, 2, 2, 1, 1, 1, 1, 0]  # sum = 12
_ANSWERS_SCORE_8  = [1, 1, 1, 1, 1, 1, 1, 1, 0]  # sum = 8
_ANSWERS_SCORE_10 = [2, 1, 2, 1, 1, 1, 1, 1, 0]  # sum = 10
_ANSWERS_SCORE_5  = [1, 1, 1, 1, 1, 0, 0, 0, 0]  # sum = 5
_ANSWERS_SCORE_3  = [1, 1, 1, 0, 0, 0, 0, 0, 0]  # sum = 3


def _make_assessment_mock(
    *,
    id: int = 1,
    user_id: int = 1,
    score: int = 8,
    severity: str = "Mild",
    days_ago: int = 0,
) -> MagicMock:
    m = MagicMock()
    m.id = id
    m.user_id = user_id
    m.score = score
    m.severity = severity
    created = datetime.now(tz=timezone.utc) - timedelta(days=days_ago)
    m.created_at = created.replace(tzinfo=None)  # SQLAlchemy stores naive UTC
    for i in range(1, 10):
        setattr(m, f"q{i}", 1)
    return m


def _make_scalar_db(scalar_value) -> AsyncMock:
    """Build an AsyncSession-like mock whose execute returns a scalar_one_or_none."""
    result_mock = MagicMock()
    result_mock.scalar_one_or_none.return_value = scalar_value

    scalars_mock = MagicMock()
    if isinstance(scalar_value, list):
        scalars_mock.all.return_value = scalar_value
    else:
        scalars_mock.all.return_value = [] if scalar_value is None else [scalar_value]

    result_mock.scalars.return_value = scalars_mock

    db = AsyncMock()
    db.execute = AsyncMock(return_value=result_mock)
    db.flush = AsyncMock()
    db.refresh = AsyncMock()
    db.add = MagicMock()
    return db


def _make_list_db(entries: list) -> AsyncMock:
    scalars_mock = MagicMock()
    scalars_mock.all.return_value = entries

    result_mock = MagicMock()
    result_mock.scalars.return_value = scalars_mock
    result_mock.scalar_one_or_none.return_value = None

    db = AsyncMock()
    db.execute = AsyncMock(return_value=result_mock)
    return db


# ---------------------------------------------------------------------------
# Service unit tests — get_phq9_reminder
# ---------------------------------------------------------------------------


class TestGetPHQ9ReminderService:
    @pytest.fixture(autouse=True)
    async def clean_db(self):  # noqa: F811
        yield

    @pytest.fixture(autouse=True)
    def mock_email(self):  # noqa: F811
        yield

    async def test_no_assessments_due_is_true(self):
        db = _make_scalar_db(None)
        result = await get_phq9_reminder(db, user_id=1)
        assert result.due is True

    async def test_no_assessments_days_since_last_is_none(self):
        db = _make_scalar_db(None)
        result = await get_phq9_reminder(db, user_id=1)
        assert result.days_since_last is None

    async def test_no_assessments_next_due_in_days_is_0(self):
        db = _make_scalar_db(None)
        result = await get_phq9_reminder(db, user_id=1)
        assert result.next_due_in_days == 0

    async def test_no_assessments_last_submitted_at_is_none(self):
        db = _make_scalar_db(None)
        result = await get_phq9_reminder(db, user_id=1)
        assert result.last_submitted_at is None

    async def test_0_days_ago_due_is_false(self):
        assessment = _make_assessment_mock(days_ago=0)
        db = _make_scalar_db(assessment)
        result = await get_phq9_reminder(db, user_id=1)
        assert result.due is False

    async def test_0_days_ago_days_since_last_is_0(self):
        assessment = _make_assessment_mock(days_ago=0)
        db = _make_scalar_db(assessment)
        result = await get_phq9_reminder(db, user_id=1)
        assert result.days_since_last == 0

    async def test_0_days_ago_next_due_in_days_is_14(self):
        assessment = _make_assessment_mock(days_ago=0)
        db = _make_scalar_db(assessment)
        result = await get_phq9_reminder(db, user_id=1)
        assert result.next_due_in_days == 14

    async def test_13_days_ago_due_is_false(self):
        assessment = _make_assessment_mock(days_ago=13)
        db = _make_scalar_db(assessment)
        result = await get_phq9_reminder(db, user_id=1)
        assert result.due is False

    async def test_13_days_ago_days_since_last_is_13(self):
        assessment = _make_assessment_mock(days_ago=13)
        db = _make_scalar_db(assessment)
        result = await get_phq9_reminder(db, user_id=1)
        assert result.days_since_last == 13

    async def test_13_days_ago_next_due_in_days_is_1(self):
        assessment = _make_assessment_mock(days_ago=13)
        db = _make_scalar_db(assessment)
        result = await get_phq9_reminder(db, user_id=1)
        assert result.next_due_in_days == 1

    async def test_14_days_ago_due_is_true(self):
        assessment = _make_assessment_mock(days_ago=14)
        db = _make_scalar_db(assessment)
        result = await get_phq9_reminder(db, user_id=1)
        assert result.due is True

    async def test_14_days_ago_days_since_last_is_14(self):
        assessment = _make_assessment_mock(days_ago=14)
        db = _make_scalar_db(assessment)
        result = await get_phq9_reminder(db, user_id=1)
        assert result.days_since_last == 14

    async def test_14_days_ago_next_due_in_days_is_0(self):
        assessment = _make_assessment_mock(days_ago=14)
        db = _make_scalar_db(assessment)
        result = await get_phq9_reminder(db, user_id=1)
        assert result.next_due_in_days == 0

    async def test_20_days_ago_due_is_true(self):
        assessment = _make_assessment_mock(days_ago=20)
        db = _make_scalar_db(assessment)
        result = await get_phq9_reminder(db, user_id=1)
        assert result.due is True

    async def test_20_days_ago_days_since_last_is_20(self):
        assessment = _make_assessment_mock(days_ago=20)
        db = _make_scalar_db(assessment)
        result = await get_phq9_reminder(db, user_id=1)
        assert result.days_since_last == 20

    async def test_20_days_ago_next_due_in_days_is_0(self):
        assessment = _make_assessment_mock(days_ago=20)
        db = _make_scalar_db(assessment)
        result = await get_phq9_reminder(db, user_id=1)
        assert result.next_due_in_days == 0


# ---------------------------------------------------------------------------
# Service unit tests — get_phq9_history (score_delta)
# ---------------------------------------------------------------------------


class TestGetPHQ9HistoryService:
    @pytest.fixture(autouse=True)
    async def clean_db(self):  # noqa: F811
        yield

    @pytest.fixture(autouse=True)
    def mock_email(self):  # noqa: F811
        yield

    async def test_single_assessment_delta_is_none(self):
        assessment = _make_assessment_mock(id=1, score=8)
        db = _make_list_db([assessment])
        pairs = await get_phq9_history(db, user_id=1)
        assert len(pairs) == 1
        _, delta = pairs[0]
        assert delta is None

    async def test_two_assessments_newest_delta_is_minus_4(self):
        """Newest score=8, previous score=12 → delta = 8-12 = -4."""
        newest = _make_assessment_mock(id=2, score=8, days_ago=0)
        oldest = _make_assessment_mock(id=1, score=12, days_ago=7)
        # get_phq9_history returns newest-first from DB
        db = _make_list_db([newest, oldest])
        pairs = await get_phq9_history(db, user_id=1)
        assert len(pairs) == 2
        _, delta_newest = pairs[0]
        assert delta_newest == -4

    async def test_two_assessments_oldest_delta_is_none(self):
        newest = _make_assessment_mock(id=2, score=8, days_ago=0)
        oldest = _make_assessment_mock(id=1, score=12, days_ago=7)
        db = _make_list_db([newest, oldest])
        pairs = await get_phq9_history(db, user_id=1)
        _, delta_oldest = pairs[1]
        assert delta_oldest is None

    async def test_three_assessments_newest_delta_is_2(self):
        """Scores: newest=10, middle=8, oldest=12.
        newest delta = 10-8 = 2."""
        newest = _make_assessment_mock(id=3, score=10, days_ago=0)
        middle = _make_assessment_mock(id=2, score=8, days_ago=7)
        oldest = _make_assessment_mock(id=1, score=12, days_ago=14)
        db = _make_list_db([newest, middle, oldest])
        pairs = await get_phq9_history(db, user_id=1)
        _, delta_newest = pairs[0]
        assert delta_newest == 2

    async def test_three_assessments_middle_delta_is_minus_4(self):
        """Middle score=8, previous score=12 → delta = 8-12 = -4."""
        newest = _make_assessment_mock(id=3, score=10, days_ago=0)
        middle = _make_assessment_mock(id=2, score=8, days_ago=7)
        oldest = _make_assessment_mock(id=1, score=12, days_ago=14)
        db = _make_list_db([newest, middle, oldest])
        pairs = await get_phq9_history(db, user_id=1)
        _, delta_middle = pairs[1]
        assert delta_middle == -4

    async def test_three_assessments_oldest_delta_is_none(self):
        newest = _make_assessment_mock(id=3, score=10, days_ago=0)
        middle = _make_assessment_mock(id=2, score=8, days_ago=7)
        oldest = _make_assessment_mock(id=1, score=12, days_ago=14)
        db = _make_list_db([newest, middle, oldest])
        pairs = await get_phq9_history(db, user_id=1)
        _, delta_oldest = pairs[2]
        assert delta_oldest is None

    async def test_empty_history_returns_empty_list(self):
        db = _make_list_db([])
        pairs = await get_phq9_history(db, user_id=1)
        assert pairs == []


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


async def _submit_phq9(client: AsyncClient, headers: dict, answers: list[int]) -> dict:
    resp = await client.post(
        "/api/v1/assessments/phq9",
        json={"answers": answers},
        headers=headers,
    )
    assert resp.status_code == 201, f"PHQ9 submit failed: {resp.text}"
    return resp.json()


# ---------------------------------------------------------------------------
# API integration tests — GET /assessments/phq9/history
# ---------------------------------------------------------------------------


class TestGetPHQ9History:
    async def test_unauthenticated_returns_401(self, client: AsyncClient):
        resp = await client.get("/api/v1/assessments/phq9/history")
        assert resp.status_code == 401

    async def test_no_assessments_returns_empty_list(self, client: AsyncClient):
        token = await _register_and_login(client, "hist_empty@test.vetlanh")
        resp = await client.get("/api/v1/assessments/phq9/history", headers=_auth_header(token))
        assert resp.status_code == 200
        assert resp.json() == []

    async def test_two_assessments_returns_newest_first(self, client: AsyncClient):
        token = await _register_and_login(client, "hist_order@test.vetlanh")
        headers = _auth_header(token)
        await _submit_phq9(client, headers, _ANSWERS_SCORE_12)
        await _submit_phq9(client, headers, _ANSWERS_SCORE_8)

        resp = await client.get("/api/v1/assessments/phq9/history", headers=headers)
        assert resp.status_code == 200
        history = resp.json()
        assert len(history) == 2
        # Newest first → score=8 first
        assert history[0]["score"] == 8
        assert history[1]["score"] == 12

    async def test_two_assessments_newest_has_correct_delta(self, client: AsyncClient):
        """First submission score=12, second score=8 → newest delta = 8-12 = -4."""
        token = await _register_and_login(client, "hist_delta@test.vetlanh")
        headers = _auth_header(token)
        await _submit_phq9(client, headers, _ANSWERS_SCORE_12)
        await _submit_phq9(client, headers, _ANSWERS_SCORE_8)

        resp = await client.get("/api/v1/assessments/phq9/history", headers=headers)
        history = resp.json()
        assert history[0]["score_delta"] == -4

    async def test_two_assessments_oldest_delta_is_null(self, client: AsyncClient):
        token = await _register_and_login(client, "hist_oldest_null@test.vetlanh")
        headers = _auth_header(token)
        await _submit_phq9(client, headers, _ANSWERS_SCORE_12)
        await _submit_phq9(client, headers, _ANSWERS_SCORE_8)

        resp = await client.get("/api/v1/assessments/phq9/history", headers=headers)
        history = resp.json()
        assert history[1]["score_delta"] is None

    async def test_response_contains_required_fields(self, client: AsyncClient):
        token = await _register_and_login(client, "hist_fields@test.vetlanh")
        headers = _auth_header(token)
        await _submit_phq9(client, headers, _ANSWERS_SCORE_5)

        resp = await client.get("/api/v1/assessments/phq9/history", headers=headers)
        entry = resp.json()[0]
        for field in ("id", "score", "severity", "answers", "questions", "submitted_at", "score_delta"):
            assert field in entry, f"Missing field: {field}"

    async def test_invalid_bearer_token_returns_401(self, client: AsyncClient):
        resp = await client.get(
            "/api/v1/assessments/phq9/history",
            headers={"Authorization": "Bearer bad.token.here"},
        )
        assert resp.status_code == 401

    async def test_history_isolated_per_user(self, client: AsyncClient):
        """User A's assessments must not appear in User B's history."""
        token_a = await _register_and_login(client, "hist_usera@test.vetlanh")
        token_b = await _register_and_login(client, "hist_userb@test.vetlanh")

        await _submit_phq9(client, _auth_header(token_a), _ANSWERS_SCORE_5)

        resp = await client.get("/api/v1/assessments/phq9/history", headers=_auth_header(token_b))
        assert resp.json() == []


# ---------------------------------------------------------------------------
# API integration tests — GET /assessments/phq9/reminder
# ---------------------------------------------------------------------------


class TestGetPHQ9Reminder:
    async def test_unauthenticated_returns_401(self, client: AsyncClient):
        resp = await client.get("/api/v1/assessments/phq9/reminder")
        assert resp.status_code == 401

    async def test_no_assessments_returns_200(self, client: AsyncClient):
        token = await _register_and_login(client, "remind_empty@test.vetlanh")
        resp = await client.get("/api/v1/assessments/phq9/reminder", headers=_auth_header(token))
        assert resp.status_code == 200

    async def test_no_assessments_due_is_true(self, client: AsyncClient):
        token = await _register_and_login(client, "remind_due_true@test.vetlanh")
        resp = await client.get("/api/v1/assessments/phq9/reminder", headers=_auth_header(token))
        assert resp.json()["due"] is True

    async def test_no_assessments_days_since_last_is_null(self, client: AsyncClient):
        token = await _register_and_login(client, "remind_null_days@test.vetlanh")
        resp = await client.get("/api/v1/assessments/phq9/reminder", headers=_auth_header(token))
        assert resp.json()["days_since_last"] is None

    async def test_no_assessments_last_submitted_at_is_null(self, client: AsyncClient):
        token = await _register_and_login(client, "remind_null_last@test.vetlanh")
        resp = await client.get("/api/v1/assessments/phq9/reminder", headers=_auth_header(token))
        assert resp.json()["last_submitted_at"] is None

    async def test_after_just_submitting_due_is_false(self, client: AsyncClient):
        token = await _register_and_login(client, "remind_just@test.vetlanh")
        headers = _auth_header(token)
        await _submit_phq9(client, headers, _ANSWERS_SCORE_5)

        resp = await client.get("/api/v1/assessments/phq9/reminder", headers=headers)
        assert resp.status_code == 200
        assert resp.json()["due"] is False

    async def test_after_just_submitting_days_since_last_is_0(self, client: AsyncClient):
        token = await _register_and_login(client, "remind_days0@test.vetlanh")
        headers = _auth_header(token)
        await _submit_phq9(client, headers, _ANSWERS_SCORE_5)

        resp = await client.get("/api/v1/assessments/phq9/reminder", headers=headers)
        assert resp.json()["days_since_last"] == 0

    async def test_after_just_submitting_next_due_in_days_is_14(self, client: AsyncClient):
        token = await _register_and_login(client, "remind_next14@test.vetlanh")
        headers = _auth_header(token)
        await _submit_phq9(client, headers, _ANSWERS_SCORE_5)

        resp = await client.get("/api/v1/assessments/phq9/reminder", headers=headers)
        assert resp.json()["next_due_in_days"] == 14

    async def test_response_contains_required_fields(self, client: AsyncClient):
        token = await _register_and_login(client, "remind_fields@test.vetlanh")
        resp = await client.get("/api/v1/assessments/phq9/reminder", headers=_auth_header(token))
        data = resp.json()
        for field in ("due", "days_since_last", "next_due_in_days", "last_submitted_at"):
            assert field in data, f"Missing field: {field}"

    async def test_invalid_bearer_token_returns_401(self, client: AsyncClient):
        resp = await client.get(
            "/api/v1/assessments/phq9/reminder",
            headers={"Authorization": "Bearer bad.token.here"},
        )
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# API integration tests — POST /assessments/phq9 score_delta
# ---------------------------------------------------------------------------


class TestPostPHQ9ScoreDelta:
    async def test_first_submission_score_delta_is_null(self, client: AsyncClient):
        token = await _register_and_login(client, "delta_first@test.vetlanh")
        result = await _submit_phq9(client, _auth_header(token), _ANSWERS_SCORE_5)
        assert result["score_delta"] is None

    async def test_second_submission_score_delta_is_correct(self, client: AsyncClient):
        """First score=12, second score=8 → delta = 8-12 = -4."""
        token = await _register_and_login(client, "delta_second@test.vetlanh")
        headers = _auth_header(token)
        first = await _submit_phq9(client, headers, _ANSWERS_SCORE_12)
        result = await _submit_phq9(client, headers, _ANSWERS_SCORE_8)
        assert result["score_delta"] == result["score"] - first["score"]

    async def test_second_submission_score_delta_negative_when_improved(self, client: AsyncClient):
        """score decreased → negative delta."""
        token = await _register_and_login(client, "delta_neg@test.vetlanh")
        headers = _auth_header(token)
        await _submit_phq9(client, headers, _ANSWERS_SCORE_12)
        result = await _submit_phq9(client, headers, _ANSWERS_SCORE_8)
        assert result["score_delta"] < 0

    async def test_second_submission_score_delta_positive_when_worsened(self, client: AsyncClient):
        """score increased → positive delta."""
        token = await _register_and_login(client, "delta_pos@test.vetlanh")
        headers = _auth_header(token)
        await _submit_phq9(client, headers, _ANSWERS_SCORE_3)
        result = await _submit_phq9(client, headers, _ANSWERS_SCORE_12)
        assert result["score_delta"] > 0

    async def test_second_submission_exact_delta_value(self, client: AsyncClient):
        """Verify the exact numeric value: score_12 first, then score_8 → delta=-4."""
        token = await _register_and_login(client, "delta_exact@test.vetlanh")
        headers = _auth_header(token)
        first = await _submit_phq9(client, headers, _ANSWERS_SCORE_12)
        second = await _submit_phq9(client, headers, _ANSWERS_SCORE_8)
        assert second["score_delta"] == second["score"] - first["score"]

    async def test_score_delta_field_present_in_response(self, client: AsyncClient):
        token = await _register_and_login(client, "delta_field@test.vetlanh")
        result = await _submit_phq9(client, _auth_header(token), _ANSWERS_SCORE_5)
        assert "score_delta" in result
