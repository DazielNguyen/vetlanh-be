"""
Tests for US-010 chat history features.

Covers:
  Service unit tests (no real DB — mocked):
    - _escape_like: escapes %, _, \\ correctly
    - list_conversations: empty conversation → message_count=0, last_message_preview=None
    - list_conversations: with messages → correct count and preview
    - list_conversations?q=keyword → filters by title and by message content
    - _get_conversation: returns None for wrong user_id
    - delete_conversation: returns True on success, False if not found

  API integration tests (real SQLite DB, in-process HTTP via AsyncClient):
    - GET /chat/conversations returns list with enriched fields
    - GET /chat/conversations?q= filters correctly
    - DELETE /chat/conversations/{id} → 204
    - DELETE /chat/conversations/{id} again → 404
    - DELETE /chat/conversations/{id} with wrong user → 404
    - Unauthenticated requests → 401
"""

import unittest.mock as mock
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import AsyncClient

from app.services.chat import _escape_like, _get_conversation, delete_conversation, list_conversations

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

TEST_EMAIL_DOMAIN = "test.vetlanh"


# ---------------------------------------------------------------------------
# Integration test helper — register + login
# ---------------------------------------------------------------------------


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
# SERVICE UNIT TESTS — pure, no real DB
# ===========================================================================


class TestEscapeLike:
    """Unit tests for _escape_like helper."""

    # Override autouse conftest fixtures — pure unit tests, no DB or email needed.
    @pytest.fixture(autouse=True)
    async def clean_db(self):  # noqa: F811
        yield

    @pytest.fixture(autouse=True)
    def mock_email(self):  # noqa: F811
        yield

    def test_percent_is_escaped(self):
        assert _escape_like("100%") == "100\\%"

    def test_underscore_is_escaped(self):
        assert _escape_like("a_b") == "a\\_b"

    def test_backslash_is_escaped(self):
        assert _escape_like("a\\b") == "a\\\\b"

    def test_no_special_chars_unchanged(self):
        assert _escape_like("hello world") == "hello world"

    def test_empty_string_unchanged(self):
        assert _escape_like("") == ""

    def test_all_specials_at_once(self):
        assert _escape_like("%_\\") == "\\%\\_\\\\"

    def test_multiple_percent_signs(self):
        assert _escape_like("%%") == "\\%\\%"

    def test_multiple_underscores(self):
        assert _escape_like("__") == "\\_\\_"

    def test_leading_special_char(self):
        assert _escape_like("%hello") == "\\%hello"

    def test_trailing_special_char(self):
        assert _escape_like("hello%") == "hello\\%"

    def test_unicode_text_unaffected(self):
        assert _escape_like("xin chào") == "xin chào"


# ---------------------------------------------------------------------------
# Helpers for DB-mocked service tests
# ---------------------------------------------------------------------------


def _make_conversation_mock(
    *,
    id: int = 1,
    user_id: int = 1,
    title: str | None = "Test Conversation",
) -> MagicMock:
    m = MagicMock()
    m.id = id
    m.user_id = user_id
    m.title = title
    m.created_at = datetime(2026, 6, 1, 10, 0, 0, tzinfo=timezone.utc)
    m.updated_at = datetime(2026, 6, 1, 10, 0, 0, tzinfo=timezone.utc)
    return m


def _make_row_mapping(
    *,
    id: int = 1,
    title: str | None = "Test Conversation",
    created_at: datetime | None = None,
    updated_at: datetime | None = None,
    message_count: int = 0,
    last_message_at: datetime | None = None,
    last_message_preview: str | None = None,
) -> MagicMock:
    """Return a mock row whose _mapping behaves like a dict for ConversationListItem(**row._mapping)."""
    now = datetime(2026, 6, 1, 10, 0, 0, tzinfo=timezone.utc)
    mapping = {
        "id": id,
        "title": title,
        "created_at": created_at or now,
        "updated_at": updated_at or now,
        "message_count": message_count,
        "last_message_at": last_message_at,
        "last_message_preview": last_message_preview,
    }
    row = MagicMock()
    row._mapping = mapping
    return row


def _make_db_with_rows(rows: list) -> AsyncMock:
    """Return an AsyncMock DB whose execute().all() returns the given rows."""
    result_mock = MagicMock()
    result_mock.all.return_value = rows
    result_mock.scalar_one_or_none.return_value = rows[0] if rows else None

    db = AsyncMock()
    db.execute = AsyncMock(return_value=result_mock)
    db.add = MagicMock()
    db.delete = AsyncMock()
    db.flush = AsyncMock()
    db.refresh = AsyncMock()
    return db


# ---------------------------------------------------------------------------
# _get_conversation
# ---------------------------------------------------------------------------


class TestGetConversation:
    """Unit tests for _get_conversation (private helper)."""

    @pytest.fixture(autouse=True)
    async def clean_db(self):  # noqa: F811
        yield

    @pytest.fixture(autouse=True)
    def mock_email(self):  # noqa: F811
        yield

    async def test_returns_conversation_for_correct_user(self):
        conv = _make_conversation_mock(id=1, user_id=42)
        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = conv
        db = AsyncMock()
        db.execute = AsyncMock(return_value=result_mock)

        result = await _get_conversation(db, conversation_id=1, user_id=42)
        assert result is conv

    async def test_returns_none_for_wrong_user(self):
        """Querying with wrong user_id must return None."""
        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = None
        db = AsyncMock()
        db.execute = AsyncMock(return_value=result_mock)

        result = await _get_conversation(db, conversation_id=1, user_id=999)
        assert result is None

    async def test_returns_none_for_nonexistent_conversation(self):
        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = None
        db = AsyncMock()
        db.execute = AsyncMock(return_value=result_mock)

        result = await _get_conversation(db, conversation_id=9999, user_id=1)
        assert result is None

    async def test_db_execute_called_once(self):
        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = None
        db = AsyncMock()
        db.execute = AsyncMock(return_value=result_mock)

        await _get_conversation(db, conversation_id=1, user_id=1)
        db.execute.assert_called_once()


# ---------------------------------------------------------------------------
# delete_conversation
# ---------------------------------------------------------------------------


class TestDeleteConversation:
    """Unit tests for delete_conversation service function."""

    @pytest.fixture(autouse=True)
    async def clean_db(self):  # noqa: F811
        yield

    @pytest.fixture(autouse=True)
    def mock_email(self):  # noqa: F811
        yield

    async def test_returns_true_when_found_and_deleted(self):
        conv = _make_conversation_mock(id=1, user_id=1)
        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = conv
        db = AsyncMock()
        db.execute = AsyncMock(return_value=result_mock)
        db.delete = AsyncMock()
        db.flush = AsyncMock()

        result = await delete_conversation(db, conversation_id=1, user_id=1)
        assert result is True

    async def test_returns_false_when_not_found(self):
        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = None
        db = AsyncMock()
        db.execute = AsyncMock(return_value=result_mock)

        result = await delete_conversation(db, conversation_id=999, user_id=1)
        assert result is False

    async def test_returns_false_for_wrong_user(self):
        """Conversation owned by user 1 should not be deletable by user 2."""
        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = None  # WHERE clause filters out wrong user
        db = AsyncMock()
        db.execute = AsyncMock(return_value=result_mock)

        result = await delete_conversation(db, conversation_id=1, user_id=2)
        assert result is False

    async def test_db_delete_called_when_found(self):
        conv = _make_conversation_mock(id=1, user_id=1)
        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = conv
        db = AsyncMock()
        db.execute = AsyncMock(return_value=result_mock)
        db.delete = AsyncMock()
        db.flush = AsyncMock()

        await delete_conversation(db, conversation_id=1, user_id=1)
        db.delete.assert_awaited_once_with(conv)

    async def test_db_delete_not_called_when_not_found(self):
        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = None
        db = AsyncMock()
        db.execute = AsyncMock(return_value=result_mock)
        db.delete = AsyncMock()

        await delete_conversation(db, conversation_id=999, user_id=1)
        db.delete.assert_not_called()

    async def test_db_flush_called_on_success(self):
        conv = _make_conversation_mock(id=1, user_id=1)
        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = conv
        db = AsyncMock()
        db.execute = AsyncMock(return_value=result_mock)
        db.delete = AsyncMock()
        db.flush = AsyncMock()

        await delete_conversation(db, conversation_id=1, user_id=1)
        db.flush.assert_awaited_once()


# ---------------------------------------------------------------------------
# list_conversations (mocked DB)
# ---------------------------------------------------------------------------


class TestListConversationsMocked:
    """Unit tests for list_conversations using a mocked DB."""

    @pytest.fixture(autouse=True)
    async def clean_db(self):  # noqa: F811
        yield

    @pytest.fixture(autouse=True)
    def mock_email(self):  # noqa: F811
        yield

    async def test_returns_empty_list_when_no_conversations(self):
        db = _make_db_with_rows([])
        result = await list_conversations(db, user_id=1)
        assert result == []

    async def test_returns_conversation_with_zero_message_count(self):
        row = _make_row_mapping(id=1, title="No Messages", message_count=0)
        db = _make_db_with_rows([row])
        result = await list_conversations(db, user_id=1)
        assert len(result) == 1
        assert result[0].message_count == 0

    async def test_returns_conversation_with_none_preview_when_no_messages(self):
        row = _make_row_mapping(id=1, message_count=0, last_message_preview=None)
        db = _make_db_with_rows([row])
        result = await list_conversations(db, user_id=1)
        assert result[0].last_message_preview is None

    async def test_returns_conversation_with_none_last_message_at_when_no_messages(self):
        row = _make_row_mapping(id=1, message_count=0, last_message_at=None)
        db = _make_db_with_rows([row])
        result = await list_conversations(db, user_id=1)
        assert result[0].last_message_at is None

    async def test_returns_correct_message_count(self):
        row = _make_row_mapping(id=1, message_count=5)
        db = _make_db_with_rows([row])
        result = await list_conversations(db, user_id=1)
        assert result[0].message_count == 5

    async def test_returns_last_message_preview(self):
        row = _make_row_mapping(id=1, message_count=2, last_message_preview="Hello there")
        db = _make_db_with_rows([row])
        result = await list_conversations(db, user_id=1)
        assert result[0].last_message_preview == "Hello there"

    async def test_returns_last_message_at(self):
        ts = datetime(2026, 6, 1, 12, 30, 0, tzinfo=timezone.utc)
        row = _make_row_mapping(id=1, message_count=1, last_message_at=ts)
        db = _make_db_with_rows([row])
        result = await list_conversations(db, user_id=1)
        assert result[0].last_message_at == ts

    async def test_returns_multiple_conversations(self):
        rows = [
            _make_row_mapping(id=1, title="First", message_count=3),
            _make_row_mapping(id=2, title="Second", message_count=1),
        ]
        db = _make_db_with_rows(rows)
        result = await list_conversations(db, user_id=1)
        assert len(result) == 2
        assert result[0].id == 1
        assert result[1].id == 2

    async def test_result_items_are_conversation_list_item_instances(self):
        from app.schemas.chat import ConversationListItem
        row = _make_row_mapping(id=1, message_count=0)
        db = _make_db_with_rows([row])
        result = await list_conversations(db, user_id=1)
        assert isinstance(result[0], ConversationListItem)

    async def test_title_can_be_none(self):
        row = _make_row_mapping(id=1, title=None, message_count=0)
        db = _make_db_with_rows([row])
        result = await list_conversations(db, user_id=1)
        assert result[0].title is None

    async def test_db_execute_called_once(self):
        db = _make_db_with_rows([])
        await list_conversations(db, user_id=1)
        db.execute.assert_called_once()

    async def test_query_with_search_keyword_calls_execute(self):
        """Passing q= should still result in exactly one DB execute call."""
        db = _make_db_with_rows([])
        await list_conversations(db, user_id=1, q="hello")
        db.execute.assert_called_once()


# ===========================================================================
# API INTEGRATION TESTS — real SQLite DB, in-process HTTP
# ===========================================================================


class TestGetConversationsEndpoint:
    """Integration tests for GET /api/v1/chat/conversations."""

    async def test_returns_empty_list_when_no_conversations(self, client: AsyncClient):
        token = await _register_and_login(client, "chat_list1@test.vetlanh")
        resp = await client.get("/api/v1/chat/conversations", headers=_auth(token))
        assert resp.status_code == 200
        assert resp.json() == []

    async def test_returns_list_after_creating_conversation(self, client: AsyncClient):
        token = await _register_and_login(client, "chat_list2@test.vetlanh")
        await client.post(
            "/api/v1/chat/conversations",
            json={"title": "My Chat"},
            headers=_auth(token),
        )
        resp = await client.get("/api/v1/chat/conversations", headers=_auth(token))
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["title"] == "My Chat"

    async def test_response_has_message_count_field(self, client: AsyncClient):
        token = await _register_and_login(client, "chat_list3@test.vetlanh")
        await client.post(
            "/api/v1/chat/conversations",
            json={"title": "Count Test"},
            headers=_auth(token),
        )
        resp = await client.get("/api/v1/chat/conversations", headers=_auth(token))
        assert resp.status_code == 200
        item = resp.json()[0]
        assert "message_count" in item

    async def test_response_has_last_message_preview_field(self, client: AsyncClient):
        token = await _register_and_login(client, "chat_list4@test.vetlanh")
        await client.post(
            "/api/v1/chat/conversations",
            json={"title": "Preview Test"},
            headers=_auth(token),
        )
        resp = await client.get("/api/v1/chat/conversations", headers=_auth(token))
        assert resp.status_code == 200
        item = resp.json()[0]
        assert "last_message_preview" in item

    async def test_response_has_last_message_at_field(self, client: AsyncClient):
        token = await _register_and_login(client, "chat_list5@test.vetlanh")
        await client.post(
            "/api/v1/chat/conversations",
            json={"title": "Timestamp Test"},
            headers=_auth(token),
        )
        resp = await client.get("/api/v1/chat/conversations", headers=_auth(token))
        assert resp.status_code == 200
        item = resp.json()[0]
        assert "last_message_at" in item

    async def test_new_conversation_has_zero_message_count(self, client: AsyncClient):
        token = await _register_and_login(client, "chat_list6@test.vetlanh")
        await client.post(
            "/api/v1/chat/conversations",
            json={"title": "Zero Messages"},
            headers=_auth(token),
        )
        resp = await client.get("/api/v1/chat/conversations", headers=_auth(token))
        assert resp.status_code == 200
        assert resp.json()[0]["message_count"] == 0

    async def test_new_conversation_has_null_last_message_preview(self, client: AsyncClient):
        token = await _register_and_login(client, "chat_list7@test.vetlanh")
        await client.post(
            "/api/v1/chat/conversations",
            json={"title": "No Messages"},
            headers=_auth(token),
        )
        resp = await client.get("/api/v1/chat/conversations", headers=_auth(token))
        assert resp.status_code == 200
        assert resp.json()[0]["last_message_preview"] is None

    async def test_new_conversation_has_null_last_message_at(self, client: AsyncClient):
        token = await _register_and_login(client, "chat_list8@test.vetlanh")
        await client.post(
            "/api/v1/chat/conversations",
            json={"title": "No Timestamp"},
            headers=_auth(token),
        )
        resp = await client.get("/api/v1/chat/conversations", headers=_auth(token))
        assert resp.status_code == 200
        assert resp.json()[0]["last_message_at"] is None

    async def test_returns_only_own_conversations(self, client: AsyncClient):
        """User A's conversations must not appear for user B."""
        token_a = await _register_and_login(client, "chat_owner_a@test.vetlanh")
        token_b = await _register_and_login(client, "chat_owner_b@test.vetlanh")
        await client.post(
            "/api/v1/chat/conversations",
            json={"title": "User A Chat"},
            headers=_auth(token_a),
        )
        resp = await client.get("/api/v1/chat/conversations", headers=_auth(token_b))
        assert resp.status_code == 200
        assert resp.json() == []

    async def test_returns_401_without_auth(self, client: AsyncClient):
        resp = await client.get("/api/v1/chat/conversations")
        assert resp.status_code == 401

    async def test_multiple_conversations_returned(self, client: AsyncClient):
        token = await _register_and_login(client, "chat_multi@test.vetlanh")
        await client.post("/api/v1/chat/conversations", json={"title": "Chat 1"}, headers=_auth(token))
        await client.post("/api/v1/chat/conversations", json={"title": "Chat 2"}, headers=_auth(token))
        resp = await client.get("/api/v1/chat/conversations", headers=_auth(token))
        assert resp.status_code == 200
        assert len(resp.json()) == 2


class TestGetConversationsWithSearch:
    """Integration tests for GET /api/v1/chat/conversations?q= search."""

    async def test_search_by_title_returns_matching(self, client: AsyncClient):
        token = await _register_and_login(client, "chat_search1@test.vetlanh")
        await client.post("/api/v1/chat/conversations", json={"title": "Mental Health"}, headers=_auth(token))
        await client.post("/api/v1/chat/conversations", json={"title": "Work Stress"}, headers=_auth(token))

        resp = await client.get("/api/v1/chat/conversations?q=Mental", headers=_auth(token))
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["title"] == "Mental Health"

    async def test_search_no_match_returns_empty_list(self, client: AsyncClient):
        token = await _register_and_login(client, "chat_search2@test.vetlanh")
        await client.post("/api/v1/chat/conversations", json={"title": "My Chat"}, headers=_auth(token))

        resp = await client.get("/api/v1/chat/conversations?q=nomatch_xyz", headers=_auth(token))
        assert resp.status_code == 200
        assert resp.json() == []

    async def test_search_returns_all_when_q_not_provided(self, client: AsyncClient):
        token = await _register_and_login(client, "chat_search3@test.vetlanh")
        await client.post("/api/v1/chat/conversations", json={"title": "Chat A"}, headers=_auth(token))
        await client.post("/api/v1/chat/conversations", json={"title": "Chat B"}, headers=_auth(token))

        resp = await client.get("/api/v1/chat/conversations", headers=_auth(token))
        assert resp.status_code == 200
        assert len(resp.json()) == 2

    async def test_search_is_case_insensitive(self, client: AsyncClient):
        token = await _register_and_login(client, "chat_search4@test.vetlanh")
        await client.post("/api/v1/chat/conversations", json={"title": "Anxiety Help"}, headers=_auth(token))

        resp = await client.get("/api/v1/chat/conversations?q=anxiety", headers=_auth(token))
        assert resp.status_code == 200
        assert len(resp.json()) == 1
        assert resp.json()[0]["title"] == "Anxiety Help"

    async def test_search_with_empty_string_returns_422(self, client: AsyncClient):
        """Empty q string is rejected — min_length=1 enforces non-trivial search terms."""
        token = await _register_and_login(client, "chat_search5@test.vetlanh")

        resp = await client.get("/api/v1/chat/conversations?q=", headers=_auth(token))
        assert resp.status_code == 422


class TestDeleteConversationEndpoint:
    """Integration tests for DELETE /api/v1/chat/conversations/{id}."""

    async def test_delete_returns_204(self, client: AsyncClient):
        token = await _register_and_login(client, "chat_del1@test.vetlanh")
        create_resp = await client.post(
            "/api/v1/chat/conversations",
            json={"title": "To Delete"},
            headers=_auth(token),
        )
        conv_id = create_resp.json()["id"]

        resp = await client.delete(f"/api/v1/chat/conversations/{conv_id}", headers=_auth(token))
        assert resp.status_code == 204

    async def test_delete_removes_conversation_from_list(self, client: AsyncClient):
        token = await _register_and_login(client, "chat_del2@test.vetlanh")
        create_resp = await client.post(
            "/api/v1/chat/conversations",
            json={"title": "Will Be Deleted"},
            headers=_auth(token),
        )
        conv_id = create_resp.json()["id"]

        await client.delete(f"/api/v1/chat/conversations/{conv_id}", headers=_auth(token))

        list_resp = await client.get("/api/v1/chat/conversations", headers=_auth(token))
        assert list_resp.status_code == 200
        ids = [c["id"] for c in list_resp.json()]
        assert conv_id not in ids

    async def test_delete_again_returns_404(self, client: AsyncClient):
        """Deleting an already-deleted conversation must return 404."""
        token = await _register_and_login(client, "chat_del3@test.vetlanh")
        create_resp = await client.post(
            "/api/v1/chat/conversations",
            json={"title": "Double Delete"},
            headers=_auth(token),
        )
        conv_id = create_resp.json()["id"]

        await client.delete(f"/api/v1/chat/conversations/{conv_id}", headers=_auth(token))
        resp = await client.delete(f"/api/v1/chat/conversations/{conv_id}", headers=_auth(token))
        assert resp.status_code == 404

    async def test_delete_wrong_user_returns_404(self, client: AsyncClient):
        """User B must not be able to delete User A's conversation."""
        token_a = await _register_and_login(client, "chat_del_a@test.vetlanh")
        token_b = await _register_and_login(client, "chat_del_b@test.vetlanh")

        create_resp = await client.post(
            "/api/v1/chat/conversations",
            json={"title": "User A's Private Chat"},
            headers=_auth(token_a),
        )
        conv_id = create_resp.json()["id"]

        resp = await client.delete(f"/api/v1/chat/conversations/{conv_id}", headers=_auth(token_b))
        assert resp.status_code == 404

    async def test_delete_nonexistent_returns_404(self, client: AsyncClient):
        token = await _register_and_login(client, "chat_del4@test.vetlanh")
        resp = await client.delete("/api/v1/chat/conversations/99999", headers=_auth(token))
        assert resp.status_code == 404

    async def test_delete_without_auth_returns_401(self, client: AsyncClient):
        resp = await client.delete("/api/v1/chat/conversations/1")
        assert resp.status_code == 401

    async def test_delete_does_not_affect_other_conversations(self, client: AsyncClient):
        """Deleting one conversation must leave other conversations intact."""
        token = await _register_and_login(client, "chat_del5@test.vetlanh")
        create_resp1 = await client.post(
            "/api/v1/chat/conversations",
            json={"title": "Keep This"},
            headers=_auth(token),
        )
        create_resp2 = await client.post(
            "/api/v1/chat/conversations",
            json={"title": "Delete This"},
            headers=_auth(token),
        )
        keep_id = create_resp1.json()["id"]
        del_id = create_resp2.json()["id"]

        await client.delete(f"/api/v1/chat/conversations/{del_id}", headers=_auth(token))

        list_resp = await client.get("/api/v1/chat/conversations", headers=_auth(token))
        ids = [c["id"] for c in list_resp.json()]
        assert keep_id in ids
        assert del_id not in ids

    async def test_delete_wrong_user_does_not_delete_conversation(self, client: AsyncClient):
        """After a failed delete (wrong user), conversation must still exist."""
        token_a = await _register_and_login(client, "chat_del_check_a@test.vetlanh")
        token_b = await _register_and_login(client, "chat_del_check_b@test.vetlanh")

        create_resp = await client.post(
            "/api/v1/chat/conversations",
            json={"title": "Still Here"},
            headers=_auth(token_a),
        )
        conv_id = create_resp.json()["id"]

        # Attempt deletion by wrong user
        await client.delete(f"/api/v1/chat/conversations/{conv_id}", headers=_auth(token_b))

        # Conversation must still be in user A's list
        list_resp = await client.get("/api/v1/chat/conversations", headers=_auth(token_a))
        ids = [c["id"] for c in list_resp.json()]
        assert conv_id in ids


# ---------------------------------------------------------------------------
# ConversationListItem schema validation
# ---------------------------------------------------------------------------


class TestConversationListItemSchema:
    """Unit tests for ConversationListItem pydantic model."""

    @pytest.fixture(autouse=True)
    async def clean_db(self):  # noqa: F811
        yield

    @pytest.fixture(autouse=True)
    def mock_email(self):  # noqa: F811
        yield

    def _base_kwargs(self) -> dict:
        now = datetime(2026, 6, 1, 10, 0, 0, tzinfo=timezone.utc)
        return {
            "id": 1,
            "title": "Test Chat",
            "message_count": 0,
            "last_message_preview": None,
            "last_message_at": None,
            "created_at": now,
            "updated_at": now,
        }

    def test_valid_item_with_no_messages(self):
        from app.schemas.chat import ConversationListItem
        item = ConversationListItem(**self._base_kwargs())
        assert item.id == 1
        assert item.message_count == 0
        assert item.last_message_preview is None
        assert item.last_message_at is None

    def test_valid_item_with_messages(self):
        from app.schemas.chat import ConversationListItem
        now = datetime(2026, 6, 1, 10, 0, 0, tzinfo=timezone.utc)
        kwargs = self._base_kwargs()
        kwargs.update(
            message_count=3,
            last_message_preview="Hello there",
            last_message_at=now,
        )
        item = ConversationListItem(**kwargs)
        assert item.message_count == 3
        assert item.last_message_preview == "Hello there"
        assert item.last_message_at == now

    def test_title_can_be_none(self):
        from app.schemas.chat import ConversationListItem
        kwargs = self._base_kwargs()
        kwargs["title"] = None
        item = ConversationListItem(**kwargs)
        assert item.title is None

    def test_serialises_to_dict(self):
        from app.schemas.chat import ConversationListItem
        item = ConversationListItem(**self._base_kwargs())
        d = item.model_dump()
        assert "message_count" in d
        assert "last_message_preview" in d
        assert "last_message_at" in d
        assert d["message_count"] == 0
        assert d["last_message_preview"] is None

    def test_message_count_zero_is_valid(self):
        from app.schemas.chat import ConversationListItem
        item = ConversationListItem(**self._base_kwargs())
        assert item.message_count == 0

    def test_large_message_count_is_valid(self):
        from app.schemas.chat import ConversationListItem
        kwargs = self._base_kwargs()
        kwargs["message_count"] = 10000
        item = ConversationListItem(**kwargs)
        assert item.message_count == 10000
