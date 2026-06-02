"""
Tests for Safety Plan feature — US-024.

Covers:
  Service unit tests (get_safety_plan, upsert_safety_plan):
    get_safety_plan:
      - returns None when no plan exists
      - returns SafetyPlanResponse when plan exists
      - trusted_contacts deserialized from "name|phone" to {name, phone}
      - plan with empty arrays returns empty lists

    upsert_safety_plan:
      - creates a new plan when none exists (db.add called)
      - updates existing plan (db.add NOT called again)
      - trusted_contacts serialized to "name|phone" format in DB
      - reasons_to_live can be None

    Helper functions (_contacts_to_db, _contacts_from_db):
      - encodes contacts to "name|phone" strings
      - decodes "name|phone" strings back to TrustedContact objects
      - entries without "|" are skipped on decode
      - empty list round-trips cleanly

  API integration tests:
    Auth:
      - GET /safety-plan → 401 without token
      - PUT /safety-plan → 401 without token

    GET /safety-plan:
      - 404 when no plan exists for user
      - 200 after plan is created
      - response has required fields
      - trusted_contacts returned as list of {name, phone} objects
      - response id is integer
      - response updated_at is present

    PUT /safety-plan:
      - 200 on first creation
      - response matches submitted data
      - trusted_contacts returned correctly as {name, phone} objects
      - second PUT replaces data (upsert behavior)
      - empty lists accepted
      - reasons_to_live can be null
      - reasons_to_live persisted correctly
      - missing optional fields use defaults
      - plans are isolated per user
      - warning_signs list stored and returned correctly
      - coping_activities list stored and returned correctly
"""

import unittest.mock as mock
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import AsyncClient

from app.schemas.safety_plan import SafetyPlanUpsert, TrustedContact
from app.services.safety_plan import (
    _contacts_from_db,
    _contacts_to_db,
    get_safety_plan,
    upsert_safety_plan,
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

TEST_EMAIL_DOMAIN = "test.vetlanh"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _register_and_login(client: AsyncClient, email: str) -> str:
    """Register a new user, verify email, log in, return Bearer token."""
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


def _make_plan_orm(
    *,
    id: int = 1,
    user_id: int = 1,
    warning_signs: list | None = None,
    coping_activities: list | None = None,
    trusted_contacts: list | None = None,
    reasons_to_live: str | None = None,
) -> MagicMock:
    m = MagicMock()
    m.id = id
    m.user_id = user_id
    m.warning_signs = warning_signs if warning_signs is not None else []
    m.coping_activities = coping_activities if coping_activities is not None else []
    m.trusted_contacts = trusted_contacts if trusted_contacts is not None else []
    m.reasons_to_live = reasons_to_live
    m.updated_at = datetime.now(tz=timezone.utc)
    return m


def _make_db_returning(plan_orm) -> AsyncMock:
    """AsyncMock db that returns *plan_orm* from scalar_one_or_none."""
    scalar_result = MagicMock()
    scalar_result.scalar_one_or_none.return_value = plan_orm

    db = AsyncMock()
    db.execute = AsyncMock(return_value=scalar_result)
    db.add = MagicMock()
    db.flush = AsyncMock()
    db.refresh = AsyncMock()
    return db


# ===========================================================================
# UNIT TESTS — helper functions
# ===========================================================================


class TestContactsHelpers:
    """Unit tests for _contacts_to_db and _contacts_from_db."""

    def test_contacts_to_db_encodes_name_and_phone(self):
        contacts = [TrustedContact(name="Alice", phone="0901234567")]
        result = _contacts_to_db(contacts)
        assert result == ["Alice|0901234567"]

    def test_contacts_to_db_multiple_contacts(self):
        contacts = [
            TrustedContact(name="Alice", phone="0901234567"),
            TrustedContact(name="Bob", phone="0987654321"),
        ]
        result = _contacts_to_db(contacts)
        assert result == ["Alice|0901234567", "Bob|0987654321"]

    def test_contacts_to_db_empty_list_returns_empty(self):
        assert _contacts_to_db([]) == []

    def test_contacts_from_db_decodes_name_and_phone(self):
        result = _contacts_from_db(["Alice|0901234567"])
        assert len(result) == 1
        assert result[0].name == "Alice"
        assert result[0].phone == "0901234567"

    def test_contacts_from_db_multiple_entries(self):
        result = _contacts_from_db(["Alice|0901234567", "Bob|0987654321"])
        assert len(result) == 2
        assert result[1].name == "Bob"

    def test_contacts_from_db_empty_list_returns_empty(self):
        assert _contacts_from_db([]) == []

    def test_contacts_from_db_skips_entries_without_pipe(self):
        result = _contacts_from_db(["NoPipe", "Alice|0901234567"])
        assert len(result) == 1
        assert result[0].name == "Alice"

    def test_contacts_round_trip(self):
        contacts = [
            TrustedContact(name="Charlie", phone="0900000001"),
            TrustedContact(name="Diana", phone="0900000002"),
        ]
        encoded = _contacts_to_db(contacts)
        decoded = _contacts_from_db(encoded)
        assert len(decoded) == 2
        assert decoded[0].name == "Charlie"
        assert decoded[0].phone == "0900000001"
        assert decoded[1].name == "Diana"
        assert decoded[1].phone == "0900000002"

    def test_contacts_from_db_phone_with_special_chars(self):
        result = _contacts_from_db(["Alice|+84-901-234-567"])
        assert result[0].phone == "+84-901-234-567"

    def test_contacts_to_db_name_with_pipe_uses_first_split_only(self):
        """A pipe in the phone field: only first pipe is the delimiter on decode."""
        contacts = [TrustedContact(name="Name", phone="012|456")]
        encoded = _contacts_to_db(contacts)
        decoded = _contacts_from_db(encoded)
        # split("|", 1) → name="Name", phone="012|456"
        assert decoded[0].name == "Name"
        assert decoded[0].phone == "012|456"


# ===========================================================================
# UNIT TESTS — get_safety_plan service
# ===========================================================================


class TestGetSafetyPlanService:

    async def test_returns_none_when_no_plan_exists(self):
        db = _make_db_returning(None)
        result = await get_safety_plan(db, user_id=1)
        assert result is None

    async def test_returns_response_when_plan_exists(self):
        plan = _make_plan_orm(trusted_contacts=[])
        db = _make_db_returning(plan)
        result = await get_safety_plan(db, user_id=1)
        assert result is not None

    async def test_response_has_correct_id(self):
        plan = _make_plan_orm(id=42, trusted_contacts=[])
        db = _make_db_returning(plan)
        result = await get_safety_plan(db, user_id=1)
        assert result.id == 42

    async def test_trusted_contacts_deserialized_correctly(self):
        plan = _make_plan_orm(trusted_contacts=["Alice|0901234567"])
        db = _make_db_returning(plan)
        result = await get_safety_plan(db, user_id=1)
        assert len(result.trusted_contacts) == 1
        assert result.trusted_contacts[0].name == "Alice"
        assert result.trusted_contacts[0].phone == "0901234567"

    async def test_empty_trusted_contacts_returns_empty_list(self):
        plan = _make_plan_orm(trusted_contacts=[])
        db = _make_db_returning(plan)
        result = await get_safety_plan(db, user_id=1)
        assert result.trusted_contacts == []

    async def test_warning_signs_returned(self):
        plan = _make_plan_orm(warning_signs=["sign1", "sign2"], trusted_contacts=[])
        db = _make_db_returning(plan)
        result = await get_safety_plan(db, user_id=1)
        assert result.warning_signs == ["sign1", "sign2"]

    async def test_reasons_to_live_can_be_none(self):
        plan = _make_plan_orm(reasons_to_live=None, trusted_contacts=[])
        db = _make_db_returning(plan)
        result = await get_safety_plan(db, user_id=1)
        assert result.reasons_to_live is None

    async def test_db_execute_called(self):
        db = _make_db_returning(None)
        await get_safety_plan(db, user_id=1)
        db.execute.assert_awaited_once()


# ===========================================================================
# UNIT TESTS — upsert_safety_plan service
# ===========================================================================


class TestUpsertSafetyPlanService:

    async def test_creates_new_plan_when_none_exists(self):
        """When no plan exists, db.add must be called once with a UserSafetyPlan instance."""
        db = _make_db_returning(None)

        # refresh must set id/updated_at on whatever object was added so _to_response works.
        # We capture the object passed to db.add and populate its missing attributes.
        added_objects: list = []

        def _capture_add(obj):
            obj.id = 99
            from datetime import datetime, timezone
            obj.updated_at = datetime.now(tz=timezone.utc)
            added_objects.append(obj)

        db.add = MagicMock(side_effect=_capture_add)
        db.refresh = AsyncMock(side_effect=lambda obj: None)

        payload = SafetyPlanUpsert(
            warning_signs=["sign"],
            coping_activities=["activity"],
            trusted_contacts=[TrustedContact(name="Alice", phone="0901234567")],
            reasons_to_live="life is good",
        )
        await upsert_safety_plan(db, user_id=1, payload=payload)

        db.add.assert_called_once()
        # The added object must be a real UserSafetyPlan instance
        from app.models.safety_plan import UserSafetyPlan
        assert isinstance(added_objects[0], UserSafetyPlan)

    async def test_updates_existing_plan_without_add(self):
        existing_plan = _make_plan_orm(
            warning_signs=["old sign"],
            trusted_contacts=[],
        )
        db = _make_db_returning(existing_plan)
        # Make refresh a no-op
        db.refresh = AsyncMock(side_effect=lambda obj: None)

        payload = SafetyPlanUpsert(
            warning_signs=["new sign"],
            coping_activities=[],
            trusted_contacts=[],
        )
        await upsert_safety_plan(db, user_id=1, payload=payload)

        db.add.assert_not_called()

    async def test_updates_warning_signs_in_place(self):
        existing_plan = _make_plan_orm(warning_signs=["old"], trusted_contacts=[])
        db = _make_db_returning(existing_plan)
        db.refresh = AsyncMock(side_effect=lambda obj: None)

        payload = SafetyPlanUpsert(warning_signs=["new1", "new2"])
        await upsert_safety_plan(db, user_id=1, payload=payload)

        assert existing_plan.warning_signs == ["new1", "new2"]

    async def test_serializes_contacts_to_pipe_format(self):
        existing_plan = _make_plan_orm(trusted_contacts=[])
        db = _make_db_returning(existing_plan)
        db.refresh = AsyncMock(side_effect=lambda obj: None)

        payload = SafetyPlanUpsert(
            trusted_contacts=[TrustedContact(name="Bob", phone="0987654321")]
        )
        await upsert_safety_plan(db, user_id=1, payload=payload)

        assert existing_plan.trusted_contacts == ["Bob|0987654321"]

    async def test_flush_and_refresh_called(self):
        existing_plan = _make_plan_orm(trusted_contacts=[])
        db = _make_db_returning(existing_plan)
        db.refresh = AsyncMock(side_effect=lambda obj: None)

        payload = SafetyPlanUpsert()
        await upsert_safety_plan(db, user_id=1, payload=payload)

        db.flush.assert_awaited_once()
        db.refresh.assert_awaited_once()

    async def test_reasons_to_live_none_accepted(self):
        existing_plan = _make_plan_orm(trusted_contacts=[])
        db = _make_db_returning(existing_plan)
        db.refresh = AsyncMock(side_effect=lambda obj: None)

        payload = SafetyPlanUpsert(reasons_to_live=None)
        await upsert_safety_plan(db, user_id=1, payload=payload)

        assert existing_plan.reasons_to_live is None


# ===========================================================================
# API INTEGRATION TESTS
# ===========================================================================


class TestSafetyPlanAPIAuth:
    """Both endpoints require authentication."""

    async def test_get_without_token_returns_401(self, client: AsyncClient):
        resp = await client.get("/api/v1/safety-plan")
        assert resp.status_code == 401

    async def test_put_without_token_returns_401(self, client: AsyncClient):
        resp = await client.put("/api/v1/safety-plan", json={})
        assert resp.status_code == 401

    async def test_get_with_invalid_token_returns_401(self, client: AsyncClient):
        resp = await client.get(
            "/api/v1/safety-plan",
            headers={"Authorization": "Bearer invalid.token.value"},
        )
        assert resp.status_code == 401


class TestGetSafetyPlanAPI:
    """GET /api/v1/safety-plan"""

    async def test_404_when_no_plan_exists(self, client: AsyncClient):
        token = await _register_and_login(client, "sp_get_404@test.vetlanh")
        resp = await client.get("/api/v1/safety-plan", headers=_auth(token))
        assert resp.status_code == 404

    async def test_404_response_has_detail_field(self, client: AsyncClient):
        token = await _register_and_login(client, "sp_get_404detail@test.vetlanh")
        resp = await client.get("/api/v1/safety-plan", headers=_auth(token))
        assert "detail" in resp.json()

    async def test_200_after_plan_created(self, client: AsyncClient):
        token = await _register_and_login(client, "sp_get_200@test.vetlanh")
        headers = _auth(token)
        await client.put("/api/v1/safety-plan", json={}, headers=headers)
        resp = await client.get("/api/v1/safety-plan", headers=headers)
        assert resp.status_code == 200

    async def test_response_has_required_fields(self, client: AsyncClient):
        token = await _register_and_login(client, "sp_get_fields@test.vetlanh")
        headers = _auth(token)
        await client.put("/api/v1/safety-plan", json={}, headers=headers)
        resp = await client.get("/api/v1/safety-plan", headers=headers)
        data = resp.json()
        for field in ("id", "warning_signs", "coping_activities", "trusted_contacts", "updated_at"):
            assert field in data, f"Missing field: {field}"

    async def test_trusted_contacts_returned_as_objects(self, client: AsyncClient):
        token = await _register_and_login(client, "sp_get_contacts@test.vetlanh")
        headers = _auth(token)
        await client.put(
            "/api/v1/safety-plan",
            json={
                "trusted_contacts": [{"name": "Alice", "phone": "0901234567"}]
            },
            headers=headers,
        )
        resp = await client.get("/api/v1/safety-plan", headers=headers)
        contacts = resp.json()["trusted_contacts"]
        assert len(contacts) == 1
        assert contacts[0]["name"] == "Alice"
        assert contacts[0]["phone"] == "0901234567"

    async def test_response_id_is_integer(self, client: AsyncClient):
        token = await _register_and_login(client, "sp_get_idtype@test.vetlanh")
        headers = _auth(token)
        await client.put("/api/v1/safety-plan", json={}, headers=headers)
        resp = await client.get("/api/v1/safety-plan", headers=headers)
        assert isinstance(resp.json()["id"], int)

    async def test_updated_at_is_present(self, client: AsyncClient):
        token = await _register_and_login(client, "sp_get_updatedat@test.vetlanh")
        headers = _auth(token)
        await client.put("/api/v1/safety-plan", json={}, headers=headers)
        resp = await client.get("/api/v1/safety-plan", headers=headers)
        assert resp.json()["updated_at"] is not None


class TestPutSafetyPlanAPI:
    """PUT /api/v1/safety-plan"""

    async def test_returns_200_on_first_creation(self, client: AsyncClient):
        token = await _register_and_login(client, "sp_put_200@test.vetlanh")
        resp = await client.put("/api/v1/safety-plan", json={}, headers=_auth(token))
        assert resp.status_code == 200

    async def test_response_matches_submitted_warning_signs(self, client: AsyncClient):
        token = await _register_and_login(client, "sp_put_signs@test.vetlanh")
        resp = await client.put(
            "/api/v1/safety-plan",
            json={"warning_signs": ["Cảm thấy cô đơn", "Không ngủ được"]},
            headers=_auth(token),
        )
        assert resp.json()["warning_signs"] == ["Cảm thấy cô đơn", "Không ngủ được"]

    async def test_response_matches_submitted_coping_activities(self, client: AsyncClient):
        token = await _register_and_login(client, "sp_put_coping@test.vetlanh")
        resp = await client.put(
            "/api/v1/safety-plan",
            json={"coping_activities": ["Đi bộ", "Nghe nhạc"]},
            headers=_auth(token),
        )
        assert resp.json()["coping_activities"] == ["Đi bộ", "Nghe nhạc"]

    async def test_trusted_contacts_returned_correctly(self, client: AsyncClient):
        token = await _register_and_login(client, "sp_put_contacts@test.vetlanh")
        resp = await client.put(
            "/api/v1/safety-plan",
            json={
                "trusted_contacts": [
                    {"name": "Mẹ", "phone": "0901234567"},
                    {"name": "Bạn thân", "phone": "0987654321"},
                ]
            },
            headers=_auth(token),
        )
        contacts = resp.json()["trusted_contacts"]
        assert len(contacts) == 2
        names = {c["name"] for c in contacts}
        assert "Mẹ" in names
        assert "Bạn thân" in names

    async def test_second_put_replaces_data(self, client: AsyncClient):
        """PUT is an upsert — second call must replace, not append."""
        token = await _register_and_login(client, "sp_put_upsert@test.vetlanh")
        headers = _auth(token)

        await client.put(
            "/api/v1/safety-plan",
            json={"warning_signs": ["old sign"]},
            headers=headers,
        )
        resp = await client.put(
            "/api/v1/safety-plan",
            json={"warning_signs": ["new sign"]},
            headers=headers,
        )
        assert resp.json()["warning_signs"] == ["new sign"]

    async def test_second_put_replaces_contacts(self, client: AsyncClient):
        token = await _register_and_login(client, "sp_put_upsert_contacts@test.vetlanh")
        headers = _auth(token)

        await client.put(
            "/api/v1/safety-plan",
            json={"trusted_contacts": [{"name": "Old", "phone": "000"}]},
            headers=headers,
        )
        resp = await client.put(
            "/api/v1/safety-plan",
            json={"trusted_contacts": [{"name": "New", "phone": "111"}]},
            headers=headers,
        )
        contacts = resp.json()["trusted_contacts"]
        assert len(contacts) == 1
        assert contacts[0]["name"] == "New"

    async def test_empty_lists_accepted(self, client: AsyncClient):
        token = await _register_and_login(client, "sp_put_empty@test.vetlanh")
        resp = await client.put(
            "/api/v1/safety-plan",
            json={"warning_signs": [], "coping_activities": [], "trusted_contacts": []},
            headers=_auth(token),
        )
        assert resp.status_code == 200
        assert resp.json()["warning_signs"] == []
        assert resp.json()["coping_activities"] == []
        assert resp.json()["trusted_contacts"] == []

    async def test_reasons_to_live_can_be_null(self, client: AsyncClient):
        token = await _register_and_login(client, "sp_put_null_rtl@test.vetlanh")
        resp = await client.put(
            "/api/v1/safety-plan",
            json={"reasons_to_live": None},
            headers=_auth(token),
        )
        assert resp.status_code == 200
        assert resp.json()["reasons_to_live"] is None

    async def test_reasons_to_live_persisted(self, client: AsyncClient):
        token = await _register_and_login(client, "sp_put_rtl@test.vetlanh")
        reason = "Gia đình tôi cần tôi"
        resp = await client.put(
            "/api/v1/safety-plan",
            json={"reasons_to_live": reason},
            headers=_auth(token),
        )
        assert resp.json()["reasons_to_live"] == reason

    async def test_empty_body_uses_defaults(self, client: AsyncClient):
        """Submitting {} should use all default values."""
        token = await _register_and_login(client, "sp_put_defaults@test.vetlanh")
        resp = await client.put("/api/v1/safety-plan", json={}, headers=_auth(token))
        assert resp.status_code == 200
        assert resp.json()["warning_signs"] == []
        assert resp.json()["coping_activities"] == []
        assert resp.json()["trusted_contacts"] == []
        assert resp.json()["reasons_to_live"] is None

    async def test_plans_isolated_per_user(self, client: AsyncClient):
        token_a = await _register_and_login(client, "sp_put_usera@test.vetlanh")
        token_b = await _register_and_login(client, "sp_put_userb@test.vetlanh")

        await client.put(
            "/api/v1/safety-plan",
            json={"warning_signs": ["user_a_sign"]},
            headers=_auth(token_a),
        )
        # User B should get 404 — their plan does not exist
        resp_b = await client.get("/api/v1/safety-plan", headers=_auth(token_b))
        assert resp_b.status_code == 404

    async def test_get_reflects_last_put(self, client: AsyncClient):
        token = await _register_and_login(client, "sp_put_reflect@test.vetlanh")
        headers = _auth(token)
        await client.put(
            "/api/v1/safety-plan",
            json={"warning_signs": ["final sign"]},
            headers=headers,
        )
        get_resp = await client.get("/api/v1/safety-plan", headers=headers)
        assert get_resp.json()["warning_signs"] == ["final sign"]

    async def test_contact_name_required_returns_422(self, client: AsyncClient):
        token = await _register_and_login(client, "sp_put_no_name@test.vetlanh")
        resp = await client.put(
            "/api/v1/safety-plan",
            json={"trusted_contacts": [{"phone": "0901234567"}]},
            headers=_auth(token),
        )
        assert resp.status_code == 422

    async def test_contact_phone_required_returns_422(self, client: AsyncClient):
        token = await _register_and_login(client, "sp_put_no_phone@test.vetlanh")
        resp = await client.put(
            "/api/v1/safety-plan",
            json={"trusted_contacts": [{"name": "Alice"}]},
            headers=_auth(token),
        )
        assert resp.status_code == 422

    async def test_response_has_id_field(self, client: AsyncClient):
        token = await _register_and_login(client, "sp_put_id@test.vetlanh")
        resp = await client.put("/api/v1/safety-plan", json={}, headers=_auth(token))
        assert "id" in resp.json()
        assert isinstance(resp.json()["id"], int)
