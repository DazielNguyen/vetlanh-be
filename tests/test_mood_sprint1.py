"""
Tests for Epic E3 Mood Tracker Sprint 1.

Covers:
  Service unit tests (no real DB — AsyncMock):
    - create_or_update_entry: creates new entry
    - create_or_update_entry: updates within 1-hour window
    - create_or_update_entry: raises 409 after edit window
    - list_entries: with and without date filters
    - update_daily_mood: is a no-op coroutine

  Schema unit tests:
    - MoodEntryCreate: valid payload
    - MoodEntryCreate: mood out-of-range rejects

  API integration tests (real DB, in-process HTTP via AsyncClient):
    - POST /mood/entries → 201 on first create
    - POST /mood/entries → 200 on update within 1 hour
    - POST /mood/entries → 409 when edit window expired
    - POST /mood/entries → 422 when mood < 1
    - POST /mood/entries → 422 when mood > 5
    - POST /mood/entries → 401 when unauthenticated
    - GET  /mood/entries → returns list ordered by date desc
    - GET  /mood/entries → filters by ?start=
    - GET  /mood/entries → filters by ?end=
    - GET  /mood/entries → filters by ?start= and ?end= combined
    - GET  /mood/entries → 401 when unauthenticated
"""

import inspect
from datetime import date, datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException
from httpx import AsyncClient
from pydantic import ValidationError

from app.schemas.mood import MoodEntryCreate, MoodEntryResponse
from app.services.mood import (
    create_or_update_entry,
    list_entries,
    update_daily_mood,
)


# ---------------------------------------------------------------------------
# Override autouse conftest fixtures for the pure-unit-test classes below.
# Integration test classes do NOT override — they inherit the real DB fixtures.
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

TEST_EMAIL_DOMAIN = "test.vetlanh"
_TODAY = date(2026, 6, 1)


def _make_mood_payload(**overrides) -> MoodEntryCreate:
    """Default valid MoodEntryCreate; pass overrides to change individual fields."""
    defaults = {
        "date": _TODAY,
        "mood": 3,
        "energy": "medium",
        "factors": ["work"],
        "note": "Feeling okay",
    }
    defaults.update(overrides)
    return MoodEntryCreate(**defaults)


def _make_mood_entry_mock(
    *,
    user_id: int = 1,
    entry_date: date = _TODAY,
    mood: int = 3,
    energy: str = "medium",
    factors: list[str] | None = None,
    note: str | None = "Feeling okay",
    created_at: datetime | None = None,
) -> MagicMock:
    """Return a MagicMock that looks like a MoodEntry ORM object."""
    if factors is None:
        factors = ["work"]
    if created_at is None:
        created_at = datetime.now(tz=timezone.utc)

    m = MagicMock()
    m.id = 1
    m.user_id = user_id
    m.date = entry_date
    m.mood = mood
    m.energy = energy
    m.factors = factors
    m.note = note
    m.created_at = created_at
    m.updated_at = datetime.now(tz=timezone.utc)
    return m


def _make_db_returning(scalar_value):
    """Build an AsyncSession-like mock whose execute returns a scalar_one_or_none."""
    result_mock = MagicMock()
    result_mock.scalar_one_or_none.return_value = scalar_value

    scalars_mock = MagicMock()
    scalars_mock.all.return_value = scalar_value if isinstance(scalar_value, list) else []

    result_mock.scalars.return_value = scalars_mock

    db = AsyncMock()
    db.execute = AsyncMock(return_value=result_mock)
    db.flush = AsyncMock()
    db.refresh = AsyncMock()
    db.add = MagicMock()
    return db


# ---------------------------------------------------------------------------
# Schema unit tests
# ---------------------------------------------------------------------------


class TestMoodEntryCreateSchema:
    @pytest.fixture(autouse=True)
    def _no_db(self):
        """No DB or email needed — pure schema tests."""
        yield

    @pytest.fixture(autouse=True)
    async def clean_db(self):  # noqa: F811
        yield

    @pytest.fixture(autouse=True)
    def mock_email(self):  # noqa: F811
        yield

    def test_valid_payload_accepted(self):
        payload = _make_mood_payload()
        assert payload.mood == 3
        assert payload.energy == "medium"
        assert payload.factors == ["work"]

    def test_mood_minimum_boundary_accepted(self):
        payload = _make_mood_payload(mood=1)
        assert payload.mood == 1

    def test_mood_maximum_boundary_accepted(self):
        payload = _make_mood_payload(mood=5)
        assert payload.mood == 5

    def test_mood_below_minimum_raises_validation_error(self):
        with pytest.raises(ValidationError):
            _make_mood_payload(mood=0)

    def test_mood_above_maximum_raises_validation_error(self):
        with pytest.raises(ValidationError):
            _make_mood_payload(mood=6)

    def test_mood_negative_raises_validation_error(self):
        with pytest.raises(ValidationError):
            _make_mood_payload(mood=-1)

    def test_note_max_length_accepted(self):
        payload = _make_mood_payload(note="x" * 500)
        assert len(payload.note) == 500

    def test_note_over_max_length_raises_validation_error(self):
        with pytest.raises(ValidationError):
            _make_mood_payload(note="x" * 501)

    def test_note_none_accepted(self):
        payload = _make_mood_payload(note=None)
        assert payload.note is None

    def test_energy_none_accepted(self):
        payload = _make_mood_payload(energy=None)
        assert payload.energy is None

    def test_energy_invalid_literal_raises_validation_error(self):
        with pytest.raises(ValidationError):
            _make_mood_payload(energy="extreme")

    def test_factors_defaults_to_empty_list(self):
        payload = MoodEntryCreate(date=_TODAY, mood=3)
        assert payload.factors == []

    def test_factors_accepts_multiple_strings(self):
        payload = _make_mood_payload(factors=["work", "family", "health"])
        assert len(payload.factors) == 3


# ---------------------------------------------------------------------------
# MoodEntryResponse schema unit tests
# ---------------------------------------------------------------------------


class TestMoodEntryResponseSchema:
    @pytest.fixture(autouse=True)
    async def clean_db(self):  # noqa: F811
        yield

    @pytest.fixture(autouse=True)
    def mock_email(self):  # noqa: F811
        yield

    def _base_kwargs(self) -> dict:
        now = datetime.now(tz=timezone.utc)
        return {
            "id": 42,
            "date": _TODAY,
            "mood": 4,
            "energy": "high",
            "factors": ["social"],
            "note": "Great day",
            "created_at": now,
            "updated_at": now,
        }

    def test_valid_response_serialises(self):
        resp = MoodEntryResponse(**self._base_kwargs())
        assert resp.id == 42
        assert resp.mood == 4

    def test_factors_empty_list_serialises(self):
        kwargs = self._base_kwargs()
        kwargs["factors"] = []
        resp = MoodEntryResponse(**kwargs)
        assert resp.factors == []

    def test_energy_none_serialises(self):
        kwargs = self._base_kwargs()
        kwargs["energy"] = None
        resp = MoodEntryResponse(**kwargs)
        assert resp.energy is None

    def test_note_none_serialises(self):
        kwargs = self._base_kwargs()
        kwargs["note"] = None
        resp = MoodEntryResponse(**kwargs)
        assert resp.note is None


# ---------------------------------------------------------------------------
# Service unit tests — create_or_update_entry
# ---------------------------------------------------------------------------


class TestCreateOrUpdateEntryService:
    @pytest.fixture(autouse=True)
    async def clean_db(self):  # noqa: F811
        yield

    @pytest.fixture(autouse=True)
    def mock_email(self):  # noqa: F811
        yield

    async def test_creates_new_entry_when_none_exists(self):
        """When no existing entry, a new MoodEntry is added and (entry, True) returned.

        We cannot patch the MoodEntry class itself because SQLAlchemy uses it as
        a column-expression source before the constructor is called.  Instead we
        let the real class be used and only mock the DB session so nothing hits
        the real database.
        """
        db = _make_db_returning(None)

        # refresh is a no-op: we just need db.add / db.flush to be recorded
        async def _refresh_side_effect(obj):
            # Simulate SQLAlchemy refreshing the object by setting created_at/updated_at
            obj.created_at = datetime.now(tz=timezone.utc)
            obj.updated_at = datetime.now(tz=timezone.utc)
            obj.id = 99

        db.refresh = AsyncMock(side_effect=_refresh_side_effect)

        entry, created = await create_or_update_entry(db, user_id=1, payload=_make_mood_payload())

        assert created is True
        db.add.assert_called_once()
        db.flush.assert_called_once()

    async def test_returns_true_created_flag_for_new_entry(self):
        """created=True signals a 201 status code to the endpoint."""
        db = _make_db_returning(None)

        async def _refresh_side_effect(obj):
            obj.created_at = datetime.now(tz=timezone.utc)
            obj.updated_at = datetime.now(tz=timezone.utc)
            obj.id = 100

        db.refresh = AsyncMock(side_effect=_refresh_side_effect)

        _, created = await create_or_update_entry(db, user_id=1, payload=_make_mood_payload())

        assert created is True

    async def test_updates_entry_within_edit_window(self):
        """Existing entry created 30 minutes ago → update allowed, created=False."""
        recent_created_at = datetime.now(tz=timezone.utc) - timedelta(minutes=30)
        existing = _make_mood_entry_mock(created_at=recent_created_at, mood=2)

        db = _make_db_returning(existing)

        payload = _make_mood_payload(mood=4)
        entry, created = await create_or_update_entry(db, user_id=1, payload=payload)

        assert created is False
        assert existing.mood == 4

    async def test_returns_false_created_flag_on_update(self):
        """created=False signals a 200 status code to the endpoint."""
        recent_created_at = datetime.now(tz=timezone.utc) - timedelta(minutes=10)
        existing = _make_mood_entry_mock(created_at=recent_created_at)

        db = _make_db_returning(existing)
        _, created = await create_or_update_entry(db, user_id=1, payload=_make_mood_payload())

        assert created is False

    async def test_updates_all_fields_within_edit_window(self):
        """All mutable fields (mood, energy, factors, note) are overwritten on update."""
        recent_created_at = datetime.now(tz=timezone.utc) - timedelta(minutes=5)
        existing = _make_mood_entry_mock(
            created_at=recent_created_at,
            mood=1,
            energy="low",
            factors=[],
            note=None,
        )
        db = _make_db_returning(existing)

        payload = _make_mood_payload(mood=5, energy="high", factors=["family", "work"], note="Updated")
        await create_or_update_entry(db, user_id=1, payload=payload)

        assert existing.mood == 5
        assert existing.energy == "high"
        assert existing.factors == ["family", "work"]
        assert existing.note == "Updated"

    async def test_raises_409_after_edit_window_expired(self):
        """Entry created 2 hours ago → 409 Conflict raised."""
        old_created_at = datetime.now(tz=timezone.utc) - timedelta(hours=2)
        existing = _make_mood_entry_mock(created_at=old_created_at)

        db = _make_db_returning(existing)

        with pytest.raises(HTTPException) as exc_info:
            await create_or_update_entry(db, user_id=1, payload=_make_mood_payload())

        assert exc_info.value.status_code == 409

    async def test_409_detail_message_present(self):
        """The 409 response carries a meaningful detail string."""
        old_created_at = datetime.now(tz=timezone.utc) - timedelta(hours=2)
        existing = _make_mood_entry_mock(created_at=old_created_at)

        db = _make_db_returning(existing)

        with pytest.raises(HTTPException) as exc_info:
            await create_or_update_entry(db, user_id=1, payload=_make_mood_payload())

        assert exc_info.value.detail  # non-empty

    async def test_exactly_at_edit_window_boundary_raises_409(self):
        """Entry created exactly 1 hour ago (now > cutoff) → 409 raised."""
        exactly_one_hour_ago = datetime.now(tz=timezone.utc) - timedelta(hours=1, seconds=1)
        existing = _make_mood_entry_mock(created_at=exactly_one_hour_ago)

        db = _make_db_returning(existing)

        with pytest.raises(HTTPException) as exc_info:
            await create_or_update_entry(db, user_id=1, payload=_make_mood_payload())

        assert exc_info.value.status_code == 409

    async def test_flush_called_on_update(self):
        """DB flush is called when updating an existing entry."""
        recent_created_at = datetime.now(tz=timezone.utc) - timedelta(minutes=20)
        existing = _make_mood_entry_mock(created_at=recent_created_at)

        db = _make_db_returning(existing)
        await create_or_update_entry(db, user_id=1, payload=_make_mood_payload())

        db.flush.assert_called_once()


# ---------------------------------------------------------------------------
# Service unit tests — list_entries
# ---------------------------------------------------------------------------


class TestListEntriesService:
    @pytest.fixture(autouse=True)
    async def clean_db(self):  # noqa: F811
        yield

    @pytest.fixture(autouse=True)
    def mock_email(self):  # noqa: F811
        yield

    def _make_list_db(self, entries: list) -> AsyncMock:
        scalars_mock = MagicMock()
        scalars_mock.all.return_value = entries

        result_mock = MagicMock()
        result_mock.scalars.return_value = scalars_mock

        db = AsyncMock()
        db.execute = AsyncMock(return_value=result_mock)
        return db

    async def test_returns_empty_list_when_no_entries(self):
        db = self._make_list_db([])
        result = await list_entries(db, user_id=1)
        assert result == []

    async def test_returns_all_entries_without_filter(self):
        entries = [_make_mood_entry_mock(), _make_mood_entry_mock()]
        db = self._make_list_db(entries)
        result = await list_entries(db, user_id=1)
        assert len(result) == 2

    async def test_executes_query(self):
        db = self._make_list_db([])
        await list_entries(db, user_id=1)
        db.execute.assert_called_once()

    async def test_returns_list_type(self):
        db = self._make_list_db([_make_mood_entry_mock()])
        result = await list_entries(db, user_id=1)
        assert isinstance(result, list)

    async def test_accepts_start_filter(self):
        """list_entries should not raise when start is provided."""
        db = self._make_list_db([])
        result = await list_entries(db, user_id=1, start=date(2026, 5, 1))
        assert result == []

    async def test_accepts_end_filter(self):
        """list_entries should not raise when end is provided."""
        db = self._make_list_db([])
        result = await list_entries(db, user_id=1, end=date(2026, 6, 30))
        assert result == []

    async def test_accepts_both_start_and_end_filters(self):
        """list_entries should not raise when both start and end are provided."""
        db = self._make_list_db([])
        result = await list_entries(db, user_id=1, start=date(2026, 5, 1), end=date(2026, 6, 30))
        assert result == []


# ---------------------------------------------------------------------------
# Service unit tests — update_daily_mood (stub / no-op)
# ---------------------------------------------------------------------------


class TestUpdateDailyMoodService:
    @pytest.fixture(autouse=True)
    async def clean_db(self):  # noqa: F811
        yield

    @pytest.fixture(autouse=True)
    def mock_email(self):  # noqa: F811
        yield

    def test_is_coroutine_function(self):
        assert inspect.iscoroutinefunction(update_daily_mood)

    async def test_runs_without_error(self):
        db = AsyncMock()
        await update_daily_mood(db, user_id=1, sentiment="positive")

    async def test_returns_none(self):
        db = AsyncMock()
        result = await update_daily_mood(db, user_id=1, sentiment="negative")
        assert result is None

    async def test_does_not_call_db(self):
        db = AsyncMock()
        await update_daily_mood(db, user_id=1, sentiment="neutral")
        db.execute.assert_not_called()
        db.commit.assert_not_called()

    async def test_accepts_positive_sentiment(self):
        db = AsyncMock()
        await update_daily_mood(db, user_id=1, sentiment="positive")

    async def test_accepts_negative_sentiment(self):
        db = AsyncMock()
        await update_daily_mood(db, user_id=2, sentiment="negative")

    async def test_accepts_neutral_sentiment(self):
        db = AsyncMock()
        await update_daily_mood(db, user_id=3, sentiment="neutral")


# ---------------------------------------------------------------------------
# Integration test helpers
# ---------------------------------------------------------------------------


async def _register_and_login(client: AsyncClient, email: str) -> str:
    """Register → verify → login → return Bearer token."""
    from unittest.mock import AsyncMock
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


def _mood_body(**overrides) -> dict:
    defaults = {
        "date": str(_TODAY),
        "mood": 3,
        "energy": "medium",
        "factors": ["work"],
        "note": "Integration test note",
    }
    defaults.update(overrides)
    return defaults


# ---------------------------------------------------------------------------
# API integration tests — POST /mood/entries
# ---------------------------------------------------------------------------


class TestPostMoodEntries:
    async def test_first_create_returns_201(self, client: AsyncClient):
        token = await _register_and_login(client, "mood_create@test.vetlanh")
        resp = await client.post(
            "/api/v1/mood/entries",
            json=_mood_body(),
            headers=_auth_header(token),
        )
        assert resp.status_code == 201

    async def test_201_response_body_contains_id(self, client: AsyncClient):
        token = await _register_and_login(client, "mood_body@test.vetlanh")
        resp = await client.post(
            "/api/v1/mood/entries",
            json=_mood_body(),
            headers=_auth_header(token),
        )
        assert "id" in resp.json()

    async def test_201_response_body_contains_mood(self, client: AsyncClient):
        token = await _register_and_login(client, "mood_mood@test.vetlanh")
        resp = await client.post(
            "/api/v1/mood/entries",
            json=_mood_body(mood=4),
            headers=_auth_header(token),
        )
        assert resp.json()["mood"] == 4

    async def test_update_within_edit_window_returns_200(self, client: AsyncClient):
        token = await _register_and_login(client, "mood_update@test.vetlanh")
        headers = _auth_header(token)
        # First create
        await client.post("/api/v1/mood/entries", json=_mood_body(mood=2), headers=headers)
        # Second call — within 1 hour (test runs fast)
        resp = await client.post("/api/v1/mood/entries", json=_mood_body(mood=3), headers=headers)
        assert resp.status_code == 200

    async def test_update_within_edit_window_persists_new_mood(self, client: AsyncClient):
        token = await _register_and_login(client, "mood_persist@test.vetlanh")
        headers = _auth_header(token)
        await client.post("/api/v1/mood/entries", json=_mood_body(mood=1), headers=headers)
        resp = await client.post("/api/v1/mood/entries", json=_mood_body(mood=5), headers=headers)
        assert resp.json()["mood"] == 5

    async def test_conflict_after_edit_window_returns_409(self, client: AsyncClient):
        """Freeze created_at to 2 hours ago so the edit window has expired."""
        token = await _register_and_login(client, "mood_409@test.vetlanh")
        headers = _auth_header(token)

        # Create the initial entry
        resp = await client.post("/api/v1/mood/entries", json=_mood_body(), headers=headers)
        assert resp.status_code == 201

        # Manipulate created_at directly in the DB to be 2 hours ago
        from app.core.database import AsyncSessionLocal
        from app.models.mood import MoodEntry
        from sqlalchemy import select, update

        entry_id = resp.json()["id"]
        two_hours_ago = datetime.now(tz=timezone.utc) - timedelta(hours=2)

        async with AsyncSessionLocal() as db:
            await db.execute(
                update(MoodEntry)
                .where(MoodEntry.id == entry_id)
                .values(created_at=two_hours_ago)
            )
            await db.commit()

        # Second attempt should now be refused
        resp2 = await client.post("/api/v1/mood/entries", json=_mood_body(mood=5), headers=headers)
        assert resp2.status_code == 409

    async def test_unauthenticated_post_returns_401(self, client: AsyncClient):
        resp = await client.post("/api/v1/mood/entries", json=_mood_body())
        assert resp.status_code == 401

    async def test_mood_below_1_returns_422(self, client: AsyncClient):
        token = await _register_and_login(client, "mood_422low@test.vetlanh")
        resp = await client.post(
            "/api/v1/mood/entries",
            json=_mood_body(mood=0),
            headers=_auth_header(token),
        )
        assert resp.status_code == 422

    async def test_mood_above_5_returns_422(self, client: AsyncClient):
        token = await _register_and_login(client, "mood_422high@test.vetlanh")
        resp = await client.post(
            "/api/v1/mood/entries",
            json=_mood_body(mood=6),
            headers=_auth_header(token),
        )
        assert resp.status_code == 422

    async def test_mood_negative_value_returns_422(self, client: AsyncClient):
        token = await _register_and_login(client, "mood_422neg@test.vetlanh")
        resp = await client.post(
            "/api/v1/mood/entries",
            json=_mood_body(mood=-1),
            headers=_auth_header(token),
        )
        assert resp.status_code == 422

    async def test_missing_mood_field_returns_422(self, client: AsyncClient):
        token = await _register_and_login(client, "mood_missing@test.vetlanh")
        body = {"date": str(_TODAY)}  # mood omitted
        resp = await client.post(
            "/api/v1/mood/entries",
            json=body,
            headers=_auth_header(token),
        )
        assert resp.status_code == 422

    async def test_invalid_bearer_token_returns_401(self, client: AsyncClient):
        resp = await client.post(
            "/api/v1/mood/entries",
            json=_mood_body(),
            headers={"Authorization": "Bearer this.is.not.valid"},
        )
        assert resp.status_code == 401

    async def test_energy_optional_field_accepted(self, client: AsyncClient):
        token = await _register_and_login(client, "mood_noenergy@test.vetlanh")
        body = _mood_body()
        body.pop("energy")
        resp = await client.post(
            "/api/v1/mood/entries",
            json=body,
            headers=_auth_header(token),
        )
        assert resp.status_code == 201

    async def test_factors_empty_list_accepted(self, client: AsyncClient):
        token = await _register_and_login(client, "mood_nofactors@test.vetlanh")
        resp = await client.post(
            "/api/v1/mood/entries",
            json=_mood_body(factors=[]),
            headers=_auth_header(token),
        )
        assert resp.status_code == 201

    async def test_note_optional_field_accepted(self, client: AsyncClient):
        token = await _register_and_login(client, "mood_nonote@test.vetlanh")
        resp = await client.post(
            "/api/v1/mood/entries",
            json=_mood_body(note=None),
            headers=_auth_header(token),
        )
        assert resp.status_code == 201


# ---------------------------------------------------------------------------
# API integration tests — GET /mood/entries
# ---------------------------------------------------------------------------


class TestGetMoodEntries:
    async def test_unauthenticated_get_returns_401(self, client: AsyncClient):
        resp = await client.get("/api/v1/mood/entries")
        assert resp.status_code == 401

    async def test_returns_empty_list_for_new_user(self, client: AsyncClient):
        token = await _register_and_login(client, "mood_empty@test.vetlanh")
        resp = await client.get("/api/v1/mood/entries", headers=_auth_header(token))
        assert resp.status_code == 200
        assert resp.json() == []

    async def test_returns_list_after_creating_entry(self, client: AsyncClient):
        token = await _register_and_login(client, "mood_list@test.vetlanh")
        headers = _auth_header(token)
        await client.post("/api/v1/mood/entries", json=_mood_body(), headers=headers)
        resp = await client.get("/api/v1/mood/entries", headers=headers)
        assert resp.status_code == 200
        assert len(resp.json()) == 1

    async def test_returns_entries_ordered_by_date_desc(self, client: AsyncClient):
        """Two entries on different dates must come back with the later date first."""
        token = await _register_and_login(client, "mood_order@test.vetlanh")
        headers = _auth_header(token)

        date_early = "2026-05-15"
        date_late = "2026-05-20"

        await client.post("/api/v1/mood/entries", json=_mood_body(date=date_early, mood=2), headers=headers)
        await client.post("/api/v1/mood/entries", json=_mood_body(date=date_late, mood=4), headers=headers)

        resp = await client.get("/api/v1/mood/entries", headers=headers)
        assert resp.status_code == 200
        entries = resp.json()
        assert len(entries) == 2
        assert entries[0]["date"] == date_late
        assert entries[1]["date"] == date_early

    async def test_filter_by_start_excludes_earlier_entries(self, client: AsyncClient):
        token = await _register_and_login(client, "mood_start@test.vetlanh")
        headers = _auth_header(token)

        await client.post("/api/v1/mood/entries", json=_mood_body(date="2026-04-01", mood=1), headers=headers)
        await client.post("/api/v1/mood/entries", json=_mood_body(date="2026-05-15", mood=3), headers=headers)

        resp = await client.get("/api/v1/mood/entries?start=2026-05-01", headers=headers)
        assert resp.status_code == 200
        entries = resp.json()
        assert all(e["date"] >= "2026-05-01" for e in entries)
        assert len(entries) == 1

    async def test_filter_by_end_excludes_later_entries(self, client: AsyncClient):
        token = await _register_and_login(client, "mood_end@test.vetlanh")
        headers = _auth_header(token)

        await client.post("/api/v1/mood/entries", json=_mood_body(date="2026-04-10", mood=2), headers=headers)
        await client.post("/api/v1/mood/entries", json=_mood_body(date="2026-05-20", mood=4), headers=headers)

        resp = await client.get("/api/v1/mood/entries?end=2026-04-30", headers=headers)
        assert resp.status_code == 200
        entries = resp.json()
        assert all(e["date"] <= "2026-04-30" for e in entries)
        assert len(entries) == 1

    async def test_filter_by_start_and_end_combined(self, client: AsyncClient):
        token = await _register_and_login(client, "mood_range@test.vetlanh")
        headers = _auth_header(token)

        await client.post("/api/v1/mood/entries", json=_mood_body(date="2026-03-01", mood=1), headers=headers)
        await client.post("/api/v1/mood/entries", json=_mood_body(date="2026-04-15", mood=3), headers=headers)
        await client.post("/api/v1/mood/entries", json=_mood_body(date="2026-06-01", mood=5), headers=headers)

        resp = await client.get(
            "/api/v1/mood/entries?start=2026-04-01&end=2026-05-31",
            headers=headers,
        )
        assert resp.status_code == 200
        entries = resp.json()
        assert len(entries) == 1
        assert entries[0]["date"] == "2026-04-15"

    async def test_start_filter_returns_empty_when_no_match(self, client: AsyncClient):
        token = await _register_and_login(client, "mood_startno@test.vetlanh")
        headers = _auth_header(token)

        await client.post("/api/v1/mood/entries", json=_mood_body(date="2026-04-01", mood=2), headers=headers)

        resp = await client.get("/api/v1/mood/entries?start=2026-05-01", headers=headers)
        assert resp.status_code == 200
        assert resp.json() == []

    async def test_entries_isolated_per_user(self, client: AsyncClient):
        """User A's entries must not appear in User B's list."""
        token_a = await _register_and_login(client, "mood_usera@test.vetlanh")
        token_b = await _register_and_login(client, "mood_userb@test.vetlanh")

        await client.post(
            "/api/v1/mood/entries",
            json=_mood_body(date="2026-05-01", mood=3),
            headers=_auth_header(token_a),
        )

        resp = await client.get("/api/v1/mood/entries", headers=_auth_header(token_b))
        assert resp.status_code == 200
        assert resp.json() == []

    async def test_response_body_contains_required_fields(self, client: AsyncClient):
        token = await _register_and_login(client, "mood_fields@test.vetlanh")
        headers = _auth_header(token)
        await client.post("/api/v1/mood/entries", json=_mood_body(), headers=headers)

        resp = await client.get("/api/v1/mood/entries", headers=headers)
        entry = resp.json()[0]
        for field in ("id", "date", "mood", "energy", "factors", "note", "created_at", "updated_at"):
            assert field in entry, f"Missing field: {field}"

    async def test_invalid_bearer_token_returns_401(self, client: AsyncClient):
        resp = await client.get(
            "/api/v1/mood/entries",
            headers={"Authorization": "Bearer bad.token.value"},
        )
        assert resp.status_code == 401
