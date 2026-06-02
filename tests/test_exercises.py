"""
Tests for Exercises feature — US-016 / US-017 / US-018 / US-020.

Covers:
  Service unit tests (no real DB — pure function / AsyncMock):
    list_exercises:
      - no filters → returns all exercises
      - mood filter → only exercises matching that mood
      - category filter → only exercises matching that category
      - mood + category → intersection
      - unknown combination returns empty list

    get_exercise:
      - known slug → returns ExerciseResponse
      - unknown slug → returns None
      - slug is case-sensitive

    get_recommended:
      - returns exercises for mood
      - respects limit
      - limit larger than available → returns all available

    log_exercise (DB layer):
      - creates UserExerciseLog with correct fields
      - db.add and db.flush called

    get_exercise_history (DB layer):
      - returns scalars from DB query

  API integration tests (real DB, in-process HTTP):
    Auth:
      - GET /exercises → 401 without token
      - GET /exercises/recommended → 401 without token
      - GET /exercises/{slug} → 401 without token
      - POST /exercises/logs → 401 without token
      - GET /exercises/logs/history → 401 without token

    GET /exercises:
      - 200 with list of all exercises
      - ?mood=anxious filters correctly
      - ?category=breathing filters correctly
      - ?mood=anxious&category=meditation works
      - invalid mood value → 422
      - invalid category value → 422

    GET /exercises/recommended:
      - 200 with list
      - mood param required → 422 when missing
      - ?mood=anxious returns ≤3 items by default
      - ?mood=anxious&limit=2 returns ≤2 items
      - limit=0 → 422 (ge=1)
      - limit=11 → 422 (le=10)

    GET /exercises/{slug}:
      - known slug → 200 with correct shape
      - breathing exercise has phases field
      - grounding exercise has steps field
      - meditation exercise has audio_url field
      - unknown slug → 404

    POST /exercises/logs:
      - 201 with correct response shape
      - duration_seconds stored correctly
      - unknown exercise_slug → 404
      - negative duration_seconds → 422
      - zero duration_seconds allowed

    GET /exercises/logs/history:
      - 200 with empty list for new user
      - returns logged entries
      - isolated per user
      - respects limit and offset
"""

import unittest.mock as mock
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import AsyncClient

from app.schemas.exercise import ExerciseCategory, ExerciseLogCreate, MoodFilter
from app.services.exercise import (
    get_exercise,
    get_exercise_history,
    get_recommended,
    list_exercises,
    log_exercise,
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

TEST_EMAIL_DOMAIN = "test.vetlanh"

# Total number of exercises in the static catalogue (update if catalogue grows)
_TOTAL_EXERCISES = 9


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_db_with_logs(logs: list) -> AsyncMock:
    scalars_mock = MagicMock()
    scalars_mock.all.return_value = logs

    result_mock = MagicMock()
    result_mock.scalars.return_value = scalars_mock

    db = AsyncMock()
    db.execute = AsyncMock(return_value=result_mock)
    db.add = MagicMock()
    db.flush = AsyncMock()
    db.refresh = AsyncMock()
    return db


def _make_log_orm_mock(
    *,
    id: int = 1,
    user_id: int = 1,
    exercise_slug: str = "box-breathing",
    duration_seconds: int = 240,
) -> MagicMock:
    m = MagicMock()
    m.id = id
    m.user_id = user_id
    m.exercise_slug = exercise_slug
    m.duration_seconds = duration_seconds
    m.created_at = datetime.now(tz=timezone.utc)
    return m


async def _register_and_login(client: AsyncClient, email: str) -> str:
    """Register a new user, verify email, login, return Bearer token."""
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
# SERVICE UNIT TESTS
# ===========================================================================


class TestListExercisesService:
    """Pure unit tests for list_exercises() — no DB needed."""

    @pytest.fixture(autouse=True)
    async def clean_db(self):
        yield

    @pytest.fixture(autouse=True)
    def mock_email(self):
        yield

    def test_no_filters_returns_all_exercises(self):
        result = list_exercises()
        assert len(result) == _TOTAL_EXERCISES

    def test_mood_filter_returns_only_matching_exercises(self):
        result = list_exercises(mood=MoodFilter.anxious)
        assert len(result) > 0
        for ex in result:
            assert MoodFilter.anxious in ex.mood_tags

    def test_category_filter_returns_only_matching_category(self):
        result = list_exercises(category=ExerciseCategory.breathing)
        assert len(result) > 0
        for ex in result:
            assert ex.category == ExerciseCategory.breathing

    def test_mood_and_category_filter_intersection(self):
        result = list_exercises(mood=MoodFilter.anxious, category=ExerciseCategory.meditation)
        assert len(result) > 0
        for ex in result:
            assert MoodFilter.anxious in ex.mood_tags
            assert ex.category == ExerciseCategory.meditation

    def test_category_grounding_returns_grounding_exercises(self):
        result = list_exercises(category=ExerciseCategory.grounding)
        assert len(result) > 0
        for ex in result:
            assert ex.category == ExerciseCategory.grounding

    def test_category_cbt_returns_empty_list(self):
        """CBT category exists in enum but has no exercises in the catalogue."""
        result = list_exercises(category=ExerciseCategory.cbt)
        assert result == []

    def test_mood_need_energy_returns_exercises(self):
        result = list_exercises(mood=MoodFilter.need_energy)
        assert len(result) > 0
        for ex in result:
            assert MoodFilter.need_energy in ex.mood_tags

    def test_mood_cant_sleep_with_category_breathing_intersection(self):
        result = list_exercises(mood=MoodFilter.cant_sleep, category=ExerciseCategory.breathing)
        for ex in result:
            assert MoodFilter.cant_sleep in ex.mood_tags
            assert ex.category == ExerciseCategory.breathing

    def test_result_items_are_exercise_response_objects(self):
        from app.schemas.exercise import ExerciseResponse
        result = list_exercises()
        for ex in result:
            assert isinstance(ex, ExerciseResponse)


class TestGetExerciseService:
    """Unit tests for get_exercise()."""

    @pytest.fixture(autouse=True)
    async def clean_db(self):
        yield

    @pytest.fixture(autouse=True)
    def mock_email(self):
        yield

    def test_known_slug_returns_exercise(self):
        result = get_exercise("box-breathing")
        assert result is not None
        assert result.slug == "box-breathing"

    def test_unknown_slug_returns_none(self):
        assert get_exercise("nonexistent-exercise") is None

    def test_empty_string_slug_returns_none(self):
        assert get_exercise("") is None

    def test_slug_is_case_sensitive(self):
        """Slug lookup must be exact — uppercase should not match."""
        assert get_exercise("Box-Breathing") is None

    def test_grounding_slug_returns_exercise(self):
        result = get_exercise("grounding-54321")
        assert result is not None
        assert result.category == ExerciseCategory.grounding

    def test_meditation_slug_returns_exercise(self):
        result = get_exercise("meditation-body-scan")
        assert result is not None
        assert result.category == ExerciseCategory.meditation

    def test_exercise_has_required_fields(self):
        ex = get_exercise("box-breathing")
        assert ex.slug
        assert ex.title
        assert ex.description
        assert ex.category
        assert ex.duration_minutes > 0
        assert len(ex.mood_tags) > 0

    def test_breathing_exercise_has_phases(self):
        ex = get_exercise("box-breathing")
        assert ex.phases is not None
        assert len(ex.phases) > 0

    def test_grounding_exercise_has_steps(self):
        ex = get_exercise("grounding-54321")
        assert ex.steps is not None
        assert len(ex.steps) > 0

    def test_meditation_exercise_has_audio_url(self):
        ex = get_exercise("meditation-body-scan")
        assert ex.audio_url is not None
        assert ex.audio_url.startswith("/")

    def test_meditation_exercise_has_audio_options(self):
        ex = get_exercise("meditation-body-scan")
        assert ex.audio_options_minutes is not None
        assert len(ex.audio_options_minutes) > 0


class TestGetRecommendedService:
    """Unit tests for get_recommended()."""

    @pytest.fixture(autouse=True)
    async def clean_db(self):
        yield

    @pytest.fixture(autouse=True)
    def mock_email(self):
        yield

    def test_returns_exercises_for_mood(self):
        result = get_recommended(mood=MoodFilter.anxious)
        assert len(result) > 0
        for ex in result:
            assert MoodFilter.anxious in ex.mood_tags

    def test_default_limit_is_three(self):
        result = get_recommended(mood=MoodFilter.anxious)
        assert len(result) <= 3

    def test_custom_limit_respected(self):
        result = get_recommended(mood=MoodFilter.anxious, limit=2)
        assert len(result) <= 2

    def test_limit_larger_than_available_returns_all(self):
        result_all = list_exercises(mood=MoodFilter.angry)
        result_recommended = get_recommended(mood=MoodFilter.angry, limit=100)
        assert len(result_recommended) == len(result_all)

    def test_limit_one_returns_at_most_one(self):
        result = get_recommended(mood=MoodFilter.anxious, limit=1)
        assert len(result) == 1


class TestLogExerciseService:
    """Unit tests for log_exercise() DB function."""

    @pytest.fixture(autouse=True)
    async def clean_db(self):
        yield

    @pytest.fixture(autouse=True)
    def mock_email(self):
        yield

    async def test_log_calls_db_add_and_flush(self):
        log_mock = _make_log_orm_mock()
        db = AsyncMock()
        db.add = MagicMock()
        db.flush = AsyncMock()
        db.refresh = AsyncMock(side_effect=lambda obj: None)

        with patch("app.services.exercise.UserExerciseLog", return_value=log_mock):
            payload = ExerciseLogCreate(exercise_slug="box-breathing", duration_seconds=240)
            result = await log_exercise(db, user_id=1, payload=payload)

        db.add.assert_called_once_with(log_mock)
        db.flush.assert_awaited_once()
        assert result.exercise_slug == "box-breathing"

    async def test_log_stores_duration_seconds(self):
        log_mock = _make_log_orm_mock(duration_seconds=360)
        db = AsyncMock()
        db.add = MagicMock()
        db.flush = AsyncMock()
        db.refresh = AsyncMock(side_effect=lambda obj: None)

        with patch("app.services.exercise.UserExerciseLog", return_value=log_mock):
            payload = ExerciseLogCreate(exercise_slug="box-breathing", duration_seconds=360)
            result = await log_exercise(db, user_id=1, payload=payload)

        assert result.duration_seconds == 360


class TestGetExerciseHistoryService:
    """Unit tests for get_exercise_history() DB function."""

    @pytest.fixture(autouse=True)
    async def clean_db(self):
        yield

    @pytest.fixture(autouse=True)
    def mock_email(self):
        yield

    async def test_returns_list_from_db(self):
        logs = [_make_log_orm_mock(id=1), _make_log_orm_mock(id=2)]
        db = _make_db_with_logs(logs)
        result = await get_exercise_history(db, user_id=1)
        assert len(result) == 2

    async def test_returns_empty_list_when_no_logs(self):
        db = _make_db_with_logs([])
        result = await get_exercise_history(db, user_id=1)
        assert result == []

    async def test_db_execute_called_once(self):
        db = _make_db_with_logs([])
        await get_exercise_history(db, user_id=1)
        db.execute.assert_awaited_once()


# ===========================================================================
# API INTEGRATION TESTS
# ===========================================================================


class TestExercisesAPIAuth:
    """All endpoints must require authentication — no token → 401."""

    async def test_list_exercises_without_token_returns_401(self, client: AsyncClient):
        resp = await client.get("/api/v1/exercises")
        assert resp.status_code == 401

    async def test_recommended_without_token_returns_401(self, client: AsyncClient):
        resp = await client.get("/api/v1/exercises/recommended?mood=anxious")
        assert resp.status_code == 401

    async def test_get_detail_without_token_returns_401(self, client: AsyncClient):
        resp = await client.get("/api/v1/exercises/box-breathing")
        assert resp.status_code == 401

    async def test_post_log_without_token_returns_401(self, client: AsyncClient):
        resp = await client.post(
            "/api/v1/exercises/logs",
            json={"exercise_slug": "box-breathing", "duration_seconds": 240},
        )
        assert resp.status_code == 401

    async def test_get_history_without_token_returns_401(self, client: AsyncClient):
        resp = await client.get("/api/v1/exercises/logs/history")
        assert resp.status_code == 401

    async def test_invalid_bearer_token_returns_401(self, client: AsyncClient):
        resp = await client.get(
            "/api/v1/exercises",
            headers={"Authorization": "Bearer invalid.token.here"},
        )
        assert resp.status_code == 401


class TestListExercisesAPI:
    """GET /api/v1/exercises"""

    async def test_returns_200(self, client: AsyncClient):
        token = await _register_and_login(client, "ex_list_200@test.vetlanh")
        resp = await client.get("/api/v1/exercises", headers=_auth(token))
        assert resp.status_code == 200

    async def test_returns_list(self, client: AsyncClient):
        token = await _register_and_login(client, "ex_list_type@test.vetlanh")
        resp = await client.get("/api/v1/exercises", headers=_auth(token))
        assert isinstance(resp.json(), list)

    async def test_returns_all_exercises(self, client: AsyncClient):
        token = await _register_and_login(client, "ex_list_all@test.vetlanh")
        resp = await client.get("/api/v1/exercises", headers=_auth(token))
        assert len(resp.json()) == _TOTAL_EXERCISES

    async def test_each_exercise_has_required_fields(self, client: AsyncClient):
        token = await _register_and_login(client, "ex_list_fields@test.vetlanh")
        resp = await client.get("/api/v1/exercises", headers=_auth(token))
        for ex in resp.json():
            for field in ("slug", "title", "description", "category", "duration_minutes", "mood_tags"):
                assert field in ex, f"Missing field '{field}' in exercise {ex.get('slug')}"

    async def test_mood_filter_anxious(self, client: AsyncClient):
        token = await _register_and_login(client, "ex_list_mood@test.vetlanh")
        resp = await client.get("/api/v1/exercises?mood=anxious", headers=_auth(token))
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) > 0
        for ex in data:
            assert "anxious" in ex["mood_tags"]

    async def test_mood_filter_sad(self, client: AsyncClient):
        token = await _register_and_login(client, "ex_list_sad@test.vetlanh")
        resp = await client.get("/api/v1/exercises?mood=sad", headers=_auth(token))
        assert resp.status_code == 200
        for ex in resp.json():
            assert "sad" in ex["mood_tags"]

    async def test_category_filter_breathing(self, client: AsyncClient):
        token = await _register_and_login(client, "ex_list_cat_br@test.vetlanh")
        resp = await client.get("/api/v1/exercises?category=breathing", headers=_auth(token))
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) > 0
        for ex in data:
            assert ex["category"] == "breathing"

    async def test_category_filter_meditation(self, client: AsyncClient):
        token = await _register_and_login(client, "ex_list_cat_med@test.vetlanh")
        resp = await client.get("/api/v1/exercises?category=meditation", headers=_auth(token))
        assert resp.status_code == 200
        for ex in resp.json():
            assert ex["category"] == "meditation"

    async def test_mood_and_category_filter_combined(self, client: AsyncClient):
        token = await _register_and_login(client, "ex_list_both@test.vetlanh")
        resp = await client.get(
            "/api/v1/exercises?mood=anxious&category=meditation", headers=_auth(token)
        )
        assert resp.status_code == 200
        for ex in resp.json():
            assert "anxious" in ex["mood_tags"]
            assert ex["category"] == "meditation"

    async def test_invalid_mood_returns_422(self, client: AsyncClient):
        token = await _register_and_login(client, "ex_list_badmood@test.vetlanh")
        resp = await client.get("/api/v1/exercises?mood=happy", headers=_auth(token))
        assert resp.status_code == 422

    async def test_invalid_category_returns_422(self, client: AsyncClient):
        token = await _register_and_login(client, "ex_list_badcat@test.vetlanh")
        resp = await client.get("/api/v1/exercises?category=yoga", headers=_auth(token))
        assert resp.status_code == 422


class TestRecommendedExercisesAPI:
    """GET /api/v1/exercises/recommended"""

    async def test_returns_200(self, client: AsyncClient):
        token = await _register_and_login(client, "ex_rec_200@test.vetlanh")
        resp = await client.get(
            "/api/v1/exercises/recommended?mood=anxious", headers=_auth(token)
        )
        assert resp.status_code == 200

    async def test_mood_required_returns_422_when_missing(self, client: AsyncClient):
        token = await _register_and_login(client, "ex_rec_nomood@test.vetlanh")
        resp = await client.get("/api/v1/exercises/recommended", headers=_auth(token))
        assert resp.status_code == 422

    async def test_default_limit_is_three_or_less(self, client: AsyncClient):
        token = await _register_and_login(client, "ex_rec_limit3@test.vetlanh")
        resp = await client.get(
            "/api/v1/exercises/recommended?mood=anxious", headers=_auth(token)
        )
        assert len(resp.json()) <= 3

    async def test_custom_limit_two(self, client: AsyncClient):
        token = await _register_and_login(client, "ex_rec_limit2@test.vetlanh")
        resp = await client.get(
            "/api/v1/exercises/recommended?mood=anxious&limit=2", headers=_auth(token)
        )
        assert len(resp.json()) <= 2

    async def test_limit_zero_returns_422(self, client: AsyncClient):
        token = await _register_and_login(client, "ex_rec_lim0@test.vetlanh")
        resp = await client.get(
            "/api/v1/exercises/recommended?mood=anxious&limit=0", headers=_auth(token)
        )
        assert resp.status_code == 422

    async def test_limit_eleven_returns_422(self, client: AsyncClient):
        token = await _register_and_login(client, "ex_rec_lim11@test.vetlanh")
        resp = await client.get(
            "/api/v1/exercises/recommended?mood=anxious&limit=11", headers=_auth(token)
        )
        assert resp.status_code == 422

    async def test_all_recommended_match_mood(self, client: AsyncClient):
        token = await _register_and_login(client, "ex_rec_match@test.vetlanh")
        resp = await client.get(
            "/api/v1/exercises/recommended?mood=sad", headers=_auth(token)
        )
        for ex in resp.json():
            assert "sad" in ex["mood_tags"]

    async def test_invalid_mood_returns_422(self, client: AsyncClient):
        token = await _register_and_login(client, "ex_rec_badmood@test.vetlanh")
        resp = await client.get(
            "/api/v1/exercises/recommended?mood=excited", headers=_auth(token)
        )
        assert resp.status_code == 422


class TestGetExerciseDetailAPI:
    """GET /api/v1/exercises/{slug}"""

    async def test_known_slug_returns_200(self, client: AsyncClient):
        token = await _register_and_login(client, "ex_detail_200@test.vetlanh")
        resp = await client.get("/api/v1/exercises/box-breathing", headers=_auth(token))
        assert resp.status_code == 200

    async def test_unknown_slug_returns_404(self, client: AsyncClient):
        token = await _register_and_login(client, "ex_detail_404@test.vetlanh")
        resp = await client.get("/api/v1/exercises/nonexistent-slug", headers=_auth(token))
        assert resp.status_code == 404

    async def test_detail_response_has_correct_shape(self, client: AsyncClient):
        token = await _register_and_login(client, "ex_detail_shape@test.vetlanh")
        resp = await client.get("/api/v1/exercises/box-breathing", headers=_auth(token))
        data = resp.json()
        for field in ("slug", "title", "description", "category", "duration_minutes", "mood_tags"):
            assert field in data

    async def test_detail_slug_matches_requested(self, client: AsyncClient):
        token = await _register_and_login(client, "ex_detail_slug@test.vetlanh")
        resp = await client.get("/api/v1/exercises/box-breathing", headers=_auth(token))
        assert resp.json()["slug"] == "box-breathing"

    async def test_breathing_exercise_has_phases(self, client: AsyncClient):
        token = await _register_and_login(client, "ex_detail_phases@test.vetlanh")
        resp = await client.get("/api/v1/exercises/box-breathing", headers=_auth(token))
        data = resp.json()
        assert data["phases"] is not None
        assert len(data["phases"]) > 0

    async def test_breathing_phase_has_label_and_seconds(self, client: AsyncClient):
        token = await _register_and_login(client, "ex_detail_phase_fields@test.vetlanh")
        resp = await client.get("/api/v1/exercises/breathing-4-7-8", headers=_auth(token))
        phase = resp.json()["phases"][0]
        assert "label" in phase
        assert "seconds" in phase

    async def test_grounding_exercise_has_steps(self, client: AsyncClient):
        token = await _register_and_login(client, "ex_detail_steps@test.vetlanh")
        resp = await client.get("/api/v1/exercises/grounding-54321", headers=_auth(token))
        data = resp.json()
        assert data["steps"] is not None
        assert len(data["steps"]) > 0

    async def test_grounding_step_has_order_and_instruction(self, client: AsyncClient):
        token = await _register_and_login(client, "ex_detail_step_fields@test.vetlanh")
        resp = await client.get("/api/v1/exercises/grounding-54321", headers=_auth(token))
        step = resp.json()["steps"][0]
        assert "order" in step
        assert "instruction" in step

    async def test_meditation_exercise_has_audio_url(self, client: AsyncClient):
        token = await _register_and_login(client, "ex_detail_audio@test.vetlanh")
        resp = await client.get("/api/v1/exercises/meditation-body-scan", headers=_auth(token))
        data = resp.json()
        assert data["audio_url"] is not None

    async def test_meditation_exercise_has_audio_options_minutes(self, client: AsyncClient):
        token = await _register_and_login(client, "ex_detail_audioopts@test.vetlanh")
        resp = await client.get("/api/v1/exercises/meditation-sleep", headers=_auth(token))
        data = resp.json()
        assert data["audio_options_minutes"] is not None
        assert len(data["audio_options_minutes"]) > 0

    async def test_404_response_has_detail_field(self, client: AsyncClient):
        token = await _register_and_login(client, "ex_detail_404msg@test.vetlanh")
        resp = await client.get("/api/v1/exercises/bad-slug", headers=_auth(token))
        assert "detail" in resp.json()


class TestLogExerciseAPI:
    """POST /api/v1/exercises/logs"""

    async def test_returns_201(self, client: AsyncClient):
        token = await _register_and_login(client, "ex_log_201@test.vetlanh")
        resp = await client.post(
            "/api/v1/exercises/logs",
            json={"exercise_slug": "box-breathing", "duration_seconds": 240},
            headers=_auth(token),
        )
        assert resp.status_code == 201

    async def test_response_has_correct_shape(self, client: AsyncClient):
        token = await _register_and_login(client, "ex_log_shape@test.vetlanh")
        resp = await client.post(
            "/api/v1/exercises/logs",
            json={"exercise_slug": "box-breathing", "duration_seconds": 240},
            headers=_auth(token),
        )
        data = resp.json()
        for field in ("id", "exercise_slug", "duration_seconds", "created_at"):
            assert field in data, f"Missing field: {field}"

    async def test_exercise_slug_stored_correctly(self, client: AsyncClient):
        token = await _register_and_login(client, "ex_log_slug@test.vetlanh")
        resp = await client.post(
            "/api/v1/exercises/logs",
            json={"exercise_slug": "grounding-54321", "duration_seconds": 300},
            headers=_auth(token),
        )
        assert resp.json()["exercise_slug"] == "grounding-54321"

    async def test_duration_seconds_stored_correctly(self, client: AsyncClient):
        token = await _register_and_login(client, "ex_log_duration@test.vetlanh")
        resp = await client.post(
            "/api/v1/exercises/logs",
            json={"exercise_slug": "box-breathing", "duration_seconds": 180},
            headers=_auth(token),
        )
        assert resp.json()["duration_seconds"] == 180

    async def test_unknown_slug_returns_404(self, client: AsyncClient):
        token = await _register_and_login(client, "ex_log_404@test.vetlanh")
        resp = await client.post(
            "/api/v1/exercises/logs",
            json={"exercise_slug": "totally-fake-exercise", "duration_seconds": 60},
            headers=_auth(token),
        )
        assert resp.status_code == 404

    async def test_negative_duration_returns_422(self, client: AsyncClient):
        token = await _register_and_login(client, "ex_log_negdur@test.vetlanh")
        resp = await client.post(
            "/api/v1/exercises/logs",
            json={"exercise_slug": "box-breathing", "duration_seconds": -1},
            headers=_auth(token),
        )
        assert resp.status_code == 422

    async def test_zero_duration_is_allowed(self, client: AsyncClient):
        token = await _register_and_login(client, "ex_log_zerodur@test.vetlanh")
        resp = await client.post(
            "/api/v1/exercises/logs",
            json={"exercise_slug": "box-breathing", "duration_seconds": 0},
            headers=_auth(token),
        )
        assert resp.status_code == 201
        assert resp.json()["duration_seconds"] == 0

    async def test_missing_slug_returns_422(self, client: AsyncClient):
        token = await _register_and_login(client, "ex_log_noslug@test.vetlanh")
        resp = await client.post(
            "/api/v1/exercises/logs",
            json={"duration_seconds": 120},
            headers=_auth(token),
        )
        assert resp.status_code == 422

    async def test_missing_duration_returns_422(self, client: AsyncClient):
        token = await _register_and_login(client, "ex_log_nodur@test.vetlanh")
        resp = await client.post(
            "/api/v1/exercises/logs",
            json={"exercise_slug": "box-breathing"},
            headers=_auth(token),
        )
        assert resp.status_code == 422

    async def test_response_id_is_integer(self, client: AsyncClient):
        token = await _register_and_login(client, "ex_log_idtype@test.vetlanh")
        resp = await client.post(
            "/api/v1/exercises/logs",
            json={"exercise_slug": "meditation-breath", "duration_seconds": 600},
            headers=_auth(token),
        )
        assert isinstance(resp.json()["id"], int)


class TestExerciseHistoryAPI:
    """GET /api/v1/exercises/logs/history"""

    async def test_returns_200(self, client: AsyncClient):
        token = await _register_and_login(client, "ex_hist_200@test.vetlanh")
        resp = await client.get("/api/v1/exercises/logs/history", headers=_auth(token))
        assert resp.status_code == 200

    async def test_empty_for_new_user(self, client: AsyncClient):
        token = await _register_and_login(client, "ex_hist_empty@test.vetlanh")
        resp = await client.get("/api/v1/exercises/logs/history", headers=_auth(token))
        assert resp.json() == []

    async def test_returns_logged_entries(self, client: AsyncClient):
        token = await _register_and_login(client, "ex_hist_entries@test.vetlanh")
        headers = _auth(token)
        await client.post(
            "/api/v1/exercises/logs",
            json={"exercise_slug": "box-breathing", "duration_seconds": 240},
            headers=headers,
        )
        resp = await client.get("/api/v1/exercises/logs/history", headers=headers)
        assert len(resp.json()) == 1

    async def test_multiple_logs_all_returned(self, client: AsyncClient):
        token = await _register_and_login(client, "ex_hist_multi@test.vetlanh")
        headers = _auth(token)
        slugs = ["box-breathing", "grounding-54321", "meditation-body-scan"]
        for slug in slugs:
            await client.post(
                "/api/v1/exercises/logs",
                json={"exercise_slug": slug, "duration_seconds": 120},
                headers=headers,
            )
        resp = await client.get("/api/v1/exercises/logs/history", headers=headers)
        assert len(resp.json()) == 3

    async def test_history_isolated_per_user(self, client: AsyncClient):
        token_a = await _register_and_login(client, "ex_hist_usera@test.vetlanh")
        token_b = await _register_and_login(client, "ex_hist_userb@test.vetlanh")

        await client.post(
            "/api/v1/exercises/logs",
            json={"exercise_slug": "box-breathing", "duration_seconds": 240},
            headers=_auth(token_a),
        )

        resp = await client.get("/api/v1/exercises/logs/history", headers=_auth(token_b))
        assert resp.json() == []

    async def test_respects_limit(self, client: AsyncClient):
        token = await _register_and_login(client, "ex_hist_limit@test.vetlanh")
        headers = _auth(token)
        for _ in range(5):
            await client.post(
                "/api/v1/exercises/logs",
                json={"exercise_slug": "box-breathing", "duration_seconds": 60},
                headers=headers,
            )
        resp = await client.get("/api/v1/exercises/logs/history?limit=3", headers=headers)
        assert len(resp.json()) == 3

    async def test_respects_offset(self, client: AsyncClient):
        token = await _register_and_login(client, "ex_hist_offset@test.vetlanh")
        headers = _auth(token)
        for _ in range(4):
            await client.post(
                "/api/v1/exercises/logs",
                json={"exercise_slug": "box-breathing", "duration_seconds": 60},
                headers=headers,
            )
        resp_all = await client.get("/api/v1/exercises/logs/history", headers=headers)
        resp_offset = await client.get(
            "/api/v1/exercises/logs/history?offset=2", headers=headers
        )
        assert len(resp_offset.json()) == 2
        assert resp_offset.json() == resp_all.json()[2:]

    async def test_limit_zero_returns_422(self, client: AsyncClient):
        token = await _register_and_login(client, "ex_hist_lim0@test.vetlanh")
        resp = await client.get(
            "/api/v1/exercises/logs/history?limit=0", headers=_auth(token)
        )
        assert resp.status_code == 422

    async def test_limit_over_100_returns_422(self, client: AsyncClient):
        token = await _register_and_login(client, "ex_hist_lim101@test.vetlanh")
        resp = await client.get(
            "/api/v1/exercises/logs/history?limit=101", headers=_auth(token)
        )
        assert resp.status_code == 422

    async def test_negative_offset_returns_422(self, client: AsyncClient):
        token = await _register_and_login(client, "ex_hist_negoff@test.vetlanh")
        resp = await client.get(
            "/api/v1/exercises/logs/history?offset=-1", headers=_auth(token)
        )
        assert resp.status_code == 422

    async def test_history_entry_has_required_fields(self, client: AsyncClient):
        token = await _register_and_login(client, "ex_hist_fields@test.vetlanh")
        headers = _auth(token)
        await client.post(
            "/api/v1/exercises/logs",
            json={"exercise_slug": "box-breathing", "duration_seconds": 240},
            headers=headers,
        )
        resp = await client.get("/api/v1/exercises/logs/history", headers=headers)
        entry = resp.json()[0]
        for field in ("id", "exercise_slug", "duration_seconds", "created_at"):
            assert field in entry
