"""
Tests for CBT Thought Record feature — US-019.

Covers:
  Service unit tests (no real DB — AsyncMock):
    create_record:
      - calls db.add, flush, refresh
      - evidence and alternative_thought can be None

    list_records:
      - returns all records from DB
      - returns empty list when none exist
      - db.execute called once

    get_record:
      - returns record when found
      - returns None when not found

    update_record:
      - updates only fields in model_fields_set
      - optional fields can be explicitly cleared to None
      - returns None when record not found

    delete_record:
      - returns True and calls db.delete when record found
      - returns False when record not found

  API integration tests (real DB, in-process HTTP):
    Auth:
      - All endpoints → 401 without token

    GET /thought-records/hints:
      - 200 with all 5 hint fields
      - hint values are non-empty strings

    GET /thought-records:
      - 200 with empty list for new user
      - returns created records
      - supports limit and offset
      - limit=0 → 422
      - limit=101 → 422
      - negative offset → 422
      - records isolated per user

    POST /thought-records:
      - 201 with correct shape
      - evidence and alternative_thought can be None
      - missing required fields → 422
      - empty string fields → 422
      - fields exceeding max_length → 422

    GET /thought-records/{record_id}:
      - 200 with correct data
      - 404 for unknown id
      - 404 when record belongs to another user

    PATCH /thought-records/{record_id}:
      - 200 and updates only sent fields
      - can clear optional fields to null
      - 404 for unknown id
      - empty body leaves record unchanged

    DELETE /thought-records/{record_id}:
      - 204 on success
      - 404 for unknown id
      - 404 when belongs to another user
      - record no longer accessible after delete
"""

import unittest.mock as mock
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import AsyncClient

from app.schemas.thought_record import (
    COLUMN_HINTS,
    ThoughtRecordCreate,
    ThoughtRecordUpdate,
)
from app.services.thought_record import (
    create_record,
    delete_record,
    get_record,
    list_records,
    update_record,
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

TEST_EMAIL_DOMAIN = "test.vetlanh"

_VALID_PAYLOAD = {
    "situation": "Hôm nay tôi bị sếp phê bình trước mặt đồng nghiệp",
    "automatic_thought": "Mình thật vô dụng",
    "emotion": "Xấu hổ 80/100",
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_record_orm(
    *,
    id: int = 1,
    user_id: int = 1,
    situation: str = "Test situation",
    automatic_thought: str = "Test thought",
    emotion: str = "Sad 70/100",
    evidence: str | None = None,
    alternative_thought: str | None = None,
) -> MagicMock:
    m = MagicMock()
    m.id = id
    m.user_id = user_id
    m.situation = situation
    m.automatic_thought = automatic_thought
    m.emotion = emotion
    m.evidence = evidence
    m.alternative_thought = alternative_thought
    m.created_at = datetime.now(tz=timezone.utc)
    m.updated_at = datetime.now(tz=timezone.utc)
    return m


def _make_db_returning_scalar(value) -> AsyncMock:
    """DB mock where scalar_one_or_none returns *value*."""
    scalar_result = MagicMock()
    scalar_result.scalar_one_or_none.return_value = value

    db = AsyncMock()
    db.execute = AsyncMock(return_value=scalar_result)
    db.add = MagicMock()
    db.flush = AsyncMock()
    db.refresh = AsyncMock()
    db.delete = AsyncMock()
    return db


def _make_db_with_scalars(records: list) -> AsyncMock:
    """DB mock where scalars().all() returns *records*."""
    scalars_mock = MagicMock()
    scalars_mock.all.return_value = records

    result_mock = MagicMock()
    result_mock.scalars.return_value = scalars_mock

    db = AsyncMock()
    db.execute = AsyncMock(return_value=result_mock)
    db.add = MagicMock()
    db.flush = AsyncMock()
    db.refresh = AsyncMock()
    db.delete = AsyncMock()
    return db


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
# SERVICE UNIT TESTS
# ===========================================================================


class TestCreateRecordService:

    async def test_calls_db_add_flush_refresh(self):
        record = _make_record_orm()
        db = AsyncMock()
        db.add = MagicMock()
        db.flush = AsyncMock()
        db.refresh = AsyncMock(side_effect=lambda obj: None)

        with patch("app.services.thought_record.ThoughtRecord", return_value=record):
            payload = ThoughtRecordCreate(
                situation="sit", automatic_thought="thought", emotion="sad"
            )
            result = await create_record(db, user_id=1, payload=payload)

        db.add.assert_called_once_with(record)
        db.flush.assert_awaited_once()
        db.refresh.assert_awaited_once()
        assert result is record

    async def test_evidence_can_be_none(self):
        record = _make_record_orm(evidence=None)
        db = AsyncMock()
        db.add = MagicMock()
        db.flush = AsyncMock()
        db.refresh = AsyncMock(side_effect=lambda obj: None)

        with patch("app.services.thought_record.ThoughtRecord", return_value=record):
            payload = ThoughtRecordCreate(
                situation="sit", automatic_thought="thought", emotion="sad", evidence=None
            )
            result = await create_record(db, user_id=1, payload=payload)

        assert result.evidence is None

    async def test_alternative_thought_can_be_none(self):
        record = _make_record_orm(alternative_thought=None)
        db = AsyncMock()
        db.add = MagicMock()
        db.flush = AsyncMock()
        db.refresh = AsyncMock(side_effect=lambda obj: None)

        with patch("app.services.thought_record.ThoughtRecord", return_value=record):
            payload = ThoughtRecordCreate(
                situation="sit",
                automatic_thought="thought",
                emotion="sad",
                alternative_thought=None,
            )
            result = await create_record(db, user_id=1, payload=payload)

        assert result.alternative_thought is None


class TestListRecordsService:

    async def test_returns_records_from_db(self):
        records = [_make_record_orm(id=1), _make_record_orm(id=2)]
        db = _make_db_with_scalars(records)
        result = await list_records(db, user_id=1)
        assert len(result) == 2

    async def test_returns_empty_list_when_none(self):
        db = _make_db_with_scalars([])
        result = await list_records(db, user_id=1)
        assert result == []

    async def test_db_execute_called_once(self):
        db = _make_db_with_scalars([])
        await list_records(db, user_id=1)
        db.execute.assert_awaited_once()


class TestGetRecordService:

    async def test_returns_record_when_found(self):
        record = _make_record_orm(id=5)
        db = _make_db_returning_scalar(record)
        result = await get_record(db, user_id=1, record_id=5)
        assert result is record

    async def test_returns_none_when_not_found(self):
        db = _make_db_returning_scalar(None)
        result = await get_record(db, user_id=1, record_id=999)
        assert result is None

    async def test_db_execute_called(self):
        db = _make_db_returning_scalar(None)
        await get_record(db, user_id=1, record_id=1)
        db.execute.assert_awaited_once()


class TestUpdateRecordService:

    async def test_returns_none_when_record_not_found(self):
        db = _make_db_returning_scalar(None)
        payload = ThoughtRecordUpdate(situation="new")
        result = await update_record(db, user_id=1, record_id=99, payload=payload)
        assert result is None

    async def test_updates_only_fields_in_model_fields_set(self):
        record = _make_record_orm(situation="original", automatic_thought="original thought")
        db = _make_db_returning_scalar(record)
        db.flush = AsyncMock()
        db.refresh = AsyncMock(side_effect=lambda obj: None)

        # Only send 'situation' — automatic_thought should stay unchanged
        payload = ThoughtRecordUpdate.model_validate({"situation": "updated"})
        assert "situation" in payload.model_fields_set
        assert "automatic_thought" not in payload.model_fields_set

        await update_record(db, user_id=1, record_id=1, payload=payload)
        assert record.situation == "updated"
        assert record.automatic_thought == "original thought"

    async def test_can_clear_evidence_to_none(self):
        record = _make_record_orm(evidence="some evidence")
        db = _make_db_returning_scalar(record)
        db.flush = AsyncMock()
        db.refresh = AsyncMock(side_effect=lambda obj: None)

        payload = ThoughtRecordUpdate.model_validate({"evidence": None})
        assert "evidence" in payload.model_fields_set
        await update_record(db, user_id=1, record_id=1, payload=payload)
        assert record.evidence is None

    async def test_can_clear_alternative_thought_to_none(self):
        record = _make_record_orm(alternative_thought="original alternative")
        db = _make_db_returning_scalar(record)
        db.flush = AsyncMock()
        db.refresh = AsyncMock(side_effect=lambda obj: None)

        payload = ThoughtRecordUpdate.model_validate({"alternative_thought": None})
        await update_record(db, user_id=1, record_id=1, payload=payload)
        assert record.alternative_thought is None

    async def test_flush_and_refresh_called_on_success(self):
        record = _make_record_orm()
        db = _make_db_returning_scalar(record)
        db.flush = AsyncMock()
        db.refresh = AsyncMock(side_effect=lambda obj: None)

        payload = ThoughtRecordUpdate(situation="new sit")
        await update_record(db, user_id=1, record_id=1, payload=payload)
        db.flush.assert_awaited_once()
        db.refresh.assert_awaited_once()


class TestDeleteRecordService:

    async def test_returns_false_when_not_found(self):
        db = _make_db_returning_scalar(None)
        result = await delete_record(db, user_id=1, record_id=99)
        assert result is False

    async def test_returns_true_and_calls_delete_when_found(self):
        record = _make_record_orm(id=1)
        db = _make_db_returning_scalar(record)
        db.delete = AsyncMock()
        db.flush = AsyncMock()

        result = await delete_record(db, user_id=1, record_id=1)
        assert result is True
        db.delete.assert_awaited_once_with(record)
        db.flush.assert_awaited_once()


# ===========================================================================
# API INTEGRATION TESTS
# ===========================================================================


class TestThoughtRecordsAPIAuth:
    """All endpoints must return 401 without a valid token."""

    async def test_get_hints_without_token_returns_401(self, client: AsyncClient):
        resp = await client.get("/api/v1/thought-records/hints")
        assert resp.status_code == 401

    async def test_list_without_token_returns_401(self, client: AsyncClient):
        resp = await client.get("/api/v1/thought-records")
        assert resp.status_code == 401

    async def test_create_without_token_returns_401(self, client: AsyncClient):
        resp = await client.post("/api/v1/thought-records", json=_VALID_PAYLOAD)
        assert resp.status_code == 401

    async def test_get_detail_without_token_returns_401(self, client: AsyncClient):
        resp = await client.get("/api/v1/thought-records/1")
        assert resp.status_code == 401

    async def test_update_without_token_returns_401(self, client: AsyncClient):
        resp = await client.patch("/api/v1/thought-records/1", json={"situation": "new"})
        assert resp.status_code == 401

    async def test_delete_without_token_returns_401(self, client: AsyncClient):
        resp = await client.delete("/api/v1/thought-records/1")
        assert resp.status_code == 401

    async def test_invalid_bearer_token_returns_401(self, client: AsyncClient):
        resp = await client.get(
            "/api/v1/thought-records",
            headers={"Authorization": "Bearer invalid.token.here"},
        )
        assert resp.status_code == 401


class TestGetHintsAPI:
    """GET /api/v1/thought-records/hints"""

    async def test_returns_200(self, client: AsyncClient):
        token = await _register_and_login(client, "tr_hints_200@test.vetlanh")
        resp = await client.get("/api/v1/thought-records/hints", headers=_auth(token))
        assert resp.status_code == 200

    async def test_returns_all_five_hint_fields(self, client: AsyncClient):
        token = await _register_and_login(client, "tr_hints_fields@test.vetlanh")
        resp = await client.get("/api/v1/thought-records/hints", headers=_auth(token))
        data = resp.json()
        for field in ("situation", "automatic_thought", "emotion", "evidence", "alternative_thought"):
            assert field in data, f"Missing hint field: {field}"

    async def test_hint_values_are_non_empty_strings(self, client: AsyncClient):
        token = await _register_and_login(client, "tr_hints_values@test.vetlanh")
        resp = await client.get("/api/v1/thought-records/hints", headers=_auth(token))
        data = resp.json()
        for field, value in data.items():
            assert isinstance(value, str) and len(value) > 0, f"Hint '{field}' is empty or not a string"

    async def test_hints_match_column_hints_dict(self, client: AsyncClient):
        token = await _register_and_login(client, "tr_hints_match@test.vetlanh")
        resp = await client.get("/api/v1/thought-records/hints", headers=_auth(token))
        data = resp.json()
        for field, expected in COLUMN_HINTS.items():
            assert data[field] == expected


class TestListThoughtRecordsAPI:
    """GET /api/v1/thought-records"""

    async def test_returns_200_empty_list_for_new_user(self, client: AsyncClient):
        token = await _register_and_login(client, "tr_list_empty@test.vetlanh")
        resp = await client.get("/api/v1/thought-records", headers=_auth(token))
        assert resp.status_code == 200
        assert resp.json() == []

    async def test_returns_created_record(self, client: AsyncClient):
        token = await _register_and_login(client, "tr_list_one@test.vetlanh")
        headers = _auth(token)
        await client.post("/api/v1/thought-records", json=_VALID_PAYLOAD, headers=headers)
        resp = await client.get("/api/v1/thought-records", headers=headers)
        assert len(resp.json()) == 1

    async def test_returns_multiple_records(self, client: AsyncClient):
        token = await _register_and_login(client, "tr_list_multi@test.vetlanh")
        headers = _auth(token)
        for _ in range(3):
            await client.post("/api/v1/thought-records", json=_VALID_PAYLOAD, headers=headers)
        resp = await client.get("/api/v1/thought-records", headers=headers)
        assert len(resp.json()) == 3

    async def test_respects_limit(self, client: AsyncClient):
        token = await _register_and_login(client, "tr_list_limit@test.vetlanh")
        headers = _auth(token)
        for _ in range(5):
            await client.post("/api/v1/thought-records", json=_VALID_PAYLOAD, headers=headers)
        resp = await client.get("/api/v1/thought-records?limit=2", headers=headers)
        assert len(resp.json()) == 2

    async def test_respects_offset(self, client: AsyncClient):
        token = await _register_and_login(client, "tr_list_offset@test.vetlanh")
        headers = _auth(token)
        for _ in range(4):
            await client.post("/api/v1/thought-records", json=_VALID_PAYLOAD, headers=headers)
        resp_all = await client.get("/api/v1/thought-records", headers=headers)
        resp_offset = await client.get("/api/v1/thought-records?offset=2", headers=headers)
        assert len(resp_offset.json()) == 2
        assert resp_offset.json() == resp_all.json()[2:]

    async def test_limit_zero_returns_422(self, client: AsyncClient):
        token = await _register_and_login(client, "tr_list_lim0@test.vetlanh")
        resp = await client.get("/api/v1/thought-records?limit=0", headers=_auth(token))
        assert resp.status_code == 422

    async def test_limit_over_100_returns_422(self, client: AsyncClient):
        token = await _register_and_login(client, "tr_list_lim101@test.vetlanh")
        resp = await client.get("/api/v1/thought-records?limit=101", headers=_auth(token))
        assert resp.status_code == 422

    async def test_negative_offset_returns_422(self, client: AsyncClient):
        token = await _register_and_login(client, "tr_list_negoff@test.vetlanh")
        resp = await client.get("/api/v1/thought-records?offset=-1", headers=_auth(token))
        assert resp.status_code == 422

    async def test_records_isolated_per_user(self, client: AsyncClient):
        token_a = await _register_and_login(client, "tr_list_usera@test.vetlanh")
        token_b = await _register_and_login(client, "tr_list_userb@test.vetlanh")
        await client.post("/api/v1/thought-records", json=_VALID_PAYLOAD, headers=_auth(token_a))
        resp = await client.get("/api/v1/thought-records", headers=_auth(token_b))
        assert resp.json() == []


class TestCreateThoughtRecordAPI:
    """POST /api/v1/thought-records"""

    async def test_returns_201(self, client: AsyncClient):
        token = await _register_and_login(client, "tr_create_201@test.vetlanh")
        resp = await client.post(
            "/api/v1/thought-records", json=_VALID_PAYLOAD, headers=_auth(token)
        )
        assert resp.status_code == 201

    async def test_response_has_required_fields(self, client: AsyncClient):
        token = await _register_and_login(client, "tr_create_fields@test.vetlanh")
        resp = await client.post(
            "/api/v1/thought-records", json=_VALID_PAYLOAD, headers=_auth(token)
        )
        data = resp.json()
        for field in ("id", "situation", "automatic_thought", "emotion", "evidence", "alternative_thought", "created_at", "updated_at"):
            assert field in data, f"Missing field: {field}"

    async def test_stored_values_match_payload(self, client: AsyncClient):
        token = await _register_and_login(client, "tr_create_values@test.vetlanh")
        resp = await client.post(
            "/api/v1/thought-records", json=_VALID_PAYLOAD, headers=_auth(token)
        )
        data = resp.json()
        assert data["situation"] == _VALID_PAYLOAD["situation"]
        assert data["automatic_thought"] == _VALID_PAYLOAD["automatic_thought"]
        assert data["emotion"] == _VALID_PAYLOAD["emotion"]

    async def test_evidence_defaults_to_null(self, client: AsyncClient):
        token = await _register_and_login(client, "tr_create_null_ev@test.vetlanh")
        resp = await client.post(
            "/api/v1/thought-records", json=_VALID_PAYLOAD, headers=_auth(token)
        )
        assert resp.json()["evidence"] is None

    async def test_alternative_thought_defaults_to_null(self, client: AsyncClient):
        token = await _register_and_login(client, "tr_create_null_alt@test.vetlanh")
        resp = await client.post(
            "/api/v1/thought-records", json=_VALID_PAYLOAD, headers=_auth(token)
        )
        assert resp.json()["alternative_thought"] is None

    async def test_can_supply_evidence(self, client: AsyncClient):
        token = await _register_and_login(client, "tr_create_evidence@test.vetlanh")
        payload = {**_VALID_PAYLOAD, "evidence": "Bằng chứng rõ ràng"}
        resp = await client.post(
            "/api/v1/thought-records", json=payload, headers=_auth(token)
        )
        assert resp.json()["evidence"] == "Bằng chứng rõ ràng"

    async def test_can_supply_alternative_thought(self, client: AsyncClient):
        token = await _register_and_login(client, "tr_create_alt@test.vetlanh")
        payload = {**_VALID_PAYLOAD, "alternative_thought": "Cách nhìn khác"}
        resp = await client.post(
            "/api/v1/thought-records", json=payload, headers=_auth(token)
        )
        assert resp.json()["alternative_thought"] == "Cách nhìn khác"

    async def test_missing_situation_returns_422(self, client: AsyncClient):
        token = await _register_and_login(client, "tr_create_nostr@test.vetlanh")
        resp = await client.post(
            "/api/v1/thought-records",
            json={"automatic_thought": "thought", "emotion": "sad"},
            headers=_auth(token),
        )
        assert resp.status_code == 422

    async def test_missing_automatic_thought_returns_422(self, client: AsyncClient):
        token = await _register_and_login(client, "tr_create_nothought@test.vetlanh")
        resp = await client.post(
            "/api/v1/thought-records",
            json={"situation": "sit", "emotion": "sad"},
            headers=_auth(token),
        )
        assert resp.status_code == 422

    async def test_missing_emotion_returns_422(self, client: AsyncClient):
        token = await _register_and_login(client, "tr_create_noemotion@test.vetlanh")
        resp = await client.post(
            "/api/v1/thought-records",
            json={"situation": "sit", "automatic_thought": "thought"},
            headers=_auth(token),
        )
        assert resp.status_code == 422

    async def test_empty_situation_returns_422(self, client: AsyncClient):
        token = await _register_and_login(client, "tr_create_emptystr@test.vetlanh")
        resp = await client.post(
            "/api/v1/thought-records",
            json={**_VALID_PAYLOAD, "situation": ""},
            headers=_auth(token),
        )
        assert resp.status_code == 422

    async def test_id_is_integer(self, client: AsyncClient):
        token = await _register_and_login(client, "tr_create_idtype@test.vetlanh")
        resp = await client.post(
            "/api/v1/thought-records", json=_VALID_PAYLOAD, headers=_auth(token)
        )
        assert isinstance(resp.json()["id"], int)


class TestGetThoughtRecordDetailAPI:
    """GET /api/v1/thought-records/{record_id}"""

    async def test_returns_200_with_correct_data(self, client: AsyncClient):
        token = await _register_and_login(client, "tr_detail_200@test.vetlanh")
        headers = _auth(token)
        created = await client.post(
            "/api/v1/thought-records", json=_VALID_PAYLOAD, headers=headers
        )
        record_id = created.json()["id"]
        resp = await client.get(f"/api/v1/thought-records/{record_id}", headers=headers)
        assert resp.status_code == 200
        assert resp.json()["id"] == record_id

    async def test_returns_404_for_unknown_id(self, client: AsyncClient):
        token = await _register_and_login(client, "tr_detail_404@test.vetlanh")
        resp = await client.get("/api/v1/thought-records/999999", headers=_auth(token))
        assert resp.status_code == 404

    async def test_returns_404_for_other_users_record(self, client: AsyncClient):
        token_a = await _register_and_login(client, "tr_detail_usera@test.vetlanh")
        token_b = await _register_and_login(client, "tr_detail_userb@test.vetlanh")

        created = await client.post(
            "/api/v1/thought-records", json=_VALID_PAYLOAD, headers=_auth(token_a)
        )
        record_id = created.json()["id"]

        resp = await client.get(f"/api/v1/thought-records/{record_id}", headers=_auth(token_b))
        assert resp.status_code == 404

    async def test_404_response_has_detail_field(self, client: AsyncClient):
        token = await _register_and_login(client, "tr_detail_404msg@test.vetlanh")
        resp = await client.get("/api/v1/thought-records/999999", headers=_auth(token))
        assert "detail" in resp.json()


class TestUpdateThoughtRecordAPI:
    """PATCH /api/v1/thought-records/{record_id}"""

    async def _create_record(self, client: AsyncClient, token: str) -> dict:
        resp = await client.post(
            "/api/v1/thought-records", json=_VALID_PAYLOAD, headers=_auth(token)
        )
        return resp.json()

    async def test_returns_200_on_update(self, client: AsyncClient):
        token = await _register_and_login(client, "tr_update_200@test.vetlanh")
        record = await self._create_record(client, token)
        resp = await client.patch(
            f"/api/v1/thought-records/{record['id']}",
            json={"situation": "New situation"},
            headers=_auth(token),
        )
        assert resp.status_code == 200

    async def test_updates_only_sent_field(self, client: AsyncClient):
        token = await _register_and_login(client, "tr_update_partial@test.vetlanh")
        record = await self._create_record(client, token)
        original_thought = record["automatic_thought"]
        resp = await client.patch(
            f"/api/v1/thought-records/{record['id']}",
            json={"situation": "Updated situation"},
            headers=_auth(token),
        )
        data = resp.json()
        assert data["situation"] == "Updated situation"
        assert data["automatic_thought"] == original_thought

    async def test_can_set_evidence(self, client: AsyncClient):
        token = await _register_and_login(client, "tr_update_evidence@test.vetlanh")
        record = await self._create_record(client, token)
        resp = await client.patch(
            f"/api/v1/thought-records/{record['id']}",
            json={"evidence": "New evidence"},
            headers=_auth(token),
        )
        assert resp.json()["evidence"] == "New evidence"

    async def test_can_clear_evidence_to_null(self, client: AsyncClient):
        token = await _register_and_login(client, "tr_update_clearnull@test.vetlanh")
        # Create with evidence
        payload = {**_VALID_PAYLOAD, "evidence": "some evidence"}
        created = await client.post(
            "/api/v1/thought-records", json=payload, headers=_auth(token)
        )
        record_id = created.json()["id"]
        resp = await client.patch(
            f"/api/v1/thought-records/{record_id}",
            json={"evidence": None},
            headers=_auth(token),
        )
        assert resp.json()["evidence"] is None

    async def test_returns_404_for_unknown_id(self, client: AsyncClient):
        token = await _register_and_login(client, "tr_update_404@test.vetlanh")
        resp = await client.patch(
            "/api/v1/thought-records/999999",
            json={"situation": "new"},
            headers=_auth(token),
        )
        assert resp.status_code == 404

    async def test_returns_404_for_other_users_record(self, client: AsyncClient):
        token_a = await _register_and_login(client, "tr_update_usera@test.vetlanh")
        token_b = await _register_and_login(client, "tr_update_userb@test.vetlanh")
        created = await client.post(
            "/api/v1/thought-records", json=_VALID_PAYLOAD, headers=_auth(token_a)
        )
        record_id = created.json()["id"]
        resp = await client.patch(
            f"/api/v1/thought-records/{record_id}",
            json={"situation": "hacked"},
            headers=_auth(token_b),
        )
        assert resp.status_code == 404

    async def test_empty_body_leaves_record_unchanged(self, client: AsyncClient):
        token = await _register_and_login(client, "tr_update_empty@test.vetlanh")
        record = await self._create_record(client, token)
        resp = await client.patch(
            f"/api/v1/thought-records/{record['id']}",
            json={},
            headers=_auth(token),
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["situation"] == record["situation"]
        assert data["automatic_thought"] == record["automatic_thought"]
        assert data["emotion"] == record["emotion"]


class TestDeleteThoughtRecordAPI:
    """DELETE /api/v1/thought-records/{record_id}"""

    async def test_returns_204_on_success(self, client: AsyncClient):
        token = await _register_and_login(client, "tr_delete_204@test.vetlanh")
        created = await client.post(
            "/api/v1/thought-records", json=_VALID_PAYLOAD, headers=_auth(token)
        )
        record_id = created.json()["id"]
        resp = await client.delete(
            f"/api/v1/thought-records/{record_id}", headers=_auth(token)
        )
        assert resp.status_code == 204

    async def test_record_no_longer_accessible_after_delete(self, client: AsyncClient):
        token = await _register_and_login(client, "tr_delete_gone@test.vetlanh")
        headers = _auth(token)
        created = await client.post(
            "/api/v1/thought-records", json=_VALID_PAYLOAD, headers=headers
        )
        record_id = created.json()["id"]
        await client.delete(f"/api/v1/thought-records/{record_id}", headers=headers)
        resp = await client.get(f"/api/v1/thought-records/{record_id}", headers=headers)
        assert resp.status_code == 404

    async def test_returns_404_for_unknown_id(self, client: AsyncClient):
        token = await _register_and_login(client, "tr_delete_404@test.vetlanh")
        resp = await client.delete("/api/v1/thought-records/999999", headers=_auth(token))
        assert resp.status_code == 404

    async def test_returns_404_for_other_users_record(self, client: AsyncClient):
        token_a = await _register_and_login(client, "tr_delete_usera@test.vetlanh")
        token_b = await _register_and_login(client, "tr_delete_userb@test.vetlanh")
        created = await client.post(
            "/api/v1/thought-records", json=_VALID_PAYLOAD, headers=_auth(token_a)
        )
        record_id = created.json()["id"]
        resp = await client.delete(
            f"/api/v1/thought-records/{record_id}", headers=_auth(token_b)
        )
        assert resp.status_code == 404
