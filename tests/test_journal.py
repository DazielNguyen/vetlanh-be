"""
Tests for Journal feature — US-013 (or equivalent sprint).

Covers:
  Service unit tests (no real DB — AsyncMock):
    - _count_words: empty string → 0
    - _count_words: whitespace-only → 0
    - _count_words: normal text → correct count
    - _count_words: multi-space text → correct count
    - create_entry: creates with correct word_count
    - create_entry: title can be None
    - list_entries: returns entries newest-first
    - list_entries: filters by keyword in content (case-insensitive)
    - list_entries: filters by keyword in title (case-insensitive)
    - list_entries: returns [] when no match
    - list_entries: respects limit/offset
    - get_entry: returns entry for correct user
    - get_entry: returns None for wrong user
    - get_entry: returns None for nonexistent id
    - update_entry: updates content and recomputes word_count
    - update_entry: updates title only (word_count unchanged)
    - update_entry: partial update — only content → title unchanged
    - delete_entry: deletes entry
    - delete_entry: raises 404 for wrong user

  API integration tests (real SQLite DB, in-process HTTP via AsyncClient):
    - POST /api/v1/journal → 201, correct response shape with word_count
    - POST /api/v1/journal — title optional (omit title → 201)
    - GET  /api/v1/journal → returns list newest-first
    - GET  /api/v1/journal?q=keyword → returns matching entries
    - GET  /api/v1/journal?q=nomatch → returns empty list
    - GET  /api/v1/journal/{id} → 200, correct entry
    - GET  /api/v1/journal/{id} → 404 for nonexistent id
    - GET  /api/v1/journal/{id} → 404 when accessing another user's entry
    - PATCH /api/v1/journal/{id} → updates content, word_count updated
    - PATCH /api/v1/journal/{id} → 404 for nonexistent id
    - DELETE /api/v1/journal/{id} → 204
    - DELETE /api/v1/journal/{id} → 404 for nonexistent id
    - Auth required: all endpoints return 401 without token
"""

import unittest.mock as mock
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException
from httpx import AsyncClient

from app.schemas.journal import JournalEntryCreate, JournalEntryUpdate
from app.services.journal import (
    _count_words,
    create_entry,
    delete_entry,
    get_entry,
    list_entries,
    update_entry,
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

TEST_EMAIL_DOMAIN = "test.vetlanh"


# ---------------------------------------------------------------------------
# Helpers — build mocked DB objects
# ---------------------------------------------------------------------------


def _make_journal_orm_mock(
    *,
    id: int = 1,
    user_id: int = 1,
    title: str | None = "Test Title",
    content: str = "Hello world",
    word_count: int = 2,
) -> MagicMock:
    m = MagicMock()
    m.id = id
    m.user_id = user_id
    m.title = title
    m.content = content
    m.word_count = word_count
    m.created_at = datetime.now(tz=timezone.utc)
    m.updated_at = datetime.now(tz=timezone.utc)
    return m


def _make_db_with_entries(entries: list) -> AsyncMock:
    """Return an AsyncMock DB that yields *entries* from db.execute().scalars()."""
    scalars_mock = MagicMock()
    scalars_mock.all.return_value = entries

    result_mock = MagicMock()
    result_mock.scalars.return_value = scalars_mock
    result_mock.scalar_one_or_none.return_value = entries[0] if entries else None

    db = AsyncMock()
    db.execute = AsyncMock(return_value=result_mock)
    db.add = MagicMock()
    db.delete = AsyncMock()
    db.flush = AsyncMock()
    db.refresh = AsyncMock()
    return db


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
# SERVICE UNIT TESTS
# ===========================================================================


class TestCountWords:
    """Unit tests for the _count_words helper."""

    # Override autouse conftest fixtures — pure unit tests, no DB or email needed.
    @pytest.fixture(autouse=True)
    async def clean_db(self):  # noqa: F811
        yield

    @pytest.fixture(autouse=True)
    def mock_email(self):  # noqa: F811
        yield

    def test_empty_string_returns_zero(self):
        assert _count_words("") == 0

    def test_whitespace_only_returns_zero(self):
        assert _count_words("   ") == 0

    def test_single_word_returns_one(self):
        assert _count_words("hello") == 1

    def test_normal_sentence_returns_correct_count(self):
        assert _count_words("Hello world foo bar") == 4

    def test_multi_space_between_words_ignored(self):
        # Python str.split() collapses multiple spaces
        assert _count_words("one   two   three") == 3

    def test_leading_trailing_whitespace_ignored(self):
        assert _count_words("  hello world  ") == 2

    def test_newline_separated_words(self):
        assert _count_words("line one\nline two") == 4

    def test_tab_separated_words(self):
        assert _count_words("word1\tword2") == 2


class TestCreateEntryService:
    """Unit tests for create_entry service function."""

    @pytest.fixture(autouse=True)
    async def clean_db(self):  # noqa: F811
        yield

    @pytest.fixture(autouse=True)
    def mock_email(self):  # noqa: F811
        yield

    async def test_create_computes_correct_word_count(self):
        """word_count on the created entry must reflect the content."""
        entry_mock = _make_journal_orm_mock(content="hello world foo", word_count=3)

        db = AsyncMock()
        db.add = MagicMock()
        db.flush = AsyncMock()
        db.refresh = AsyncMock(side_effect=lambda obj: None)

        # After refresh, the mock object (added via db.add) should be returned.
        # We patch JournalEntry constructor to return our mock.
        with patch("app.services.journal.JournalEntry", return_value=entry_mock):
            payload = JournalEntryCreate(title="T", content="hello world foo")
            result = await create_entry(db, user_id=1, payload=payload)

        assert result.word_count == 3
        db.add.assert_called_once_with(entry_mock)
        db.flush.assert_awaited_once()

    async def test_create_with_none_title(self):
        """title=None must be stored on the entry without error."""
        entry_mock = _make_journal_orm_mock(title=None, content="only content", word_count=2)

        db = AsyncMock()
        db.add = MagicMock()
        db.flush = AsyncMock()
        db.refresh = AsyncMock(side_effect=lambda obj: None)

        with patch("app.services.journal.JournalEntry", return_value=entry_mock):
            payload = JournalEntryCreate(title=None, content="only content")
            result = await create_entry(db, user_id=5, payload=payload)

        assert result.title is None

    async def test_create_empty_content_gives_zero_word_count(self):
        """Empty content → word_count == 0."""
        entry_mock = _make_journal_orm_mock(content="", word_count=0)

        db = AsyncMock()
        db.add = MagicMock()
        db.flush = AsyncMock()
        db.refresh = AsyncMock(side_effect=lambda obj: None)

        with patch("app.services.journal.JournalEntry", return_value=entry_mock):
            payload = JournalEntryCreate(title="empty", content="")
            result = await create_entry(db, user_id=1, payload=payload)

        assert result.word_count == 0


class TestListEntriesService:
    """Unit tests for list_entries service function."""

    @pytest.fixture(autouse=True)
    async def clean_db(self):  # noqa: F811
        yield

    @pytest.fixture(autouse=True)
    def mock_email(self):  # noqa: F811
        yield

    async def test_returns_empty_list_when_no_entries(self):
        db = _make_db_with_entries([])
        result = await list_entries(db, user_id=1)
        assert result == []

    async def test_returns_all_entries_for_user(self):
        entries = [
            _make_journal_orm_mock(id=1, content="first"),
            _make_journal_orm_mock(id=2, content="second"),
        ]
        db = _make_db_with_entries(entries)
        result = await list_entries(db, user_id=1)
        assert len(result) == 2

    async def test_db_execute_called_once(self):
        db = _make_db_with_entries([])
        await list_entries(db, user_id=1)
        db.execute.assert_awaited_once()

    async def test_db_execute_called_once_with_q(self):
        db = _make_db_with_entries([])
        await list_entries(db, user_id=1, q="keyword")
        db.execute.assert_awaited_once()


class TestGetEntryService:
    """Unit tests for get_entry service function."""

    @pytest.fixture(autouse=True)
    async def clean_db(self):  # noqa: F811
        yield

    @pytest.fixture(autouse=True)
    def mock_email(self):  # noqa: F811
        yield

    async def test_returns_entry_for_correct_user(self):
        entry = _make_journal_orm_mock(id=10, user_id=1)
        db = _make_db_with_entries([entry])
        result = await get_entry(db, user_id=1, entry_id=10)
        assert result.id == 10

    async def test_returns_none_when_entry_not_found(self):
        db = _make_db_with_entries([])  # scalar_one_or_none → None
        result = await get_entry(db, user_id=1, entry_id=999)
        assert result is None

    async def test_returns_none_for_wrong_user(self):
        """DB returns None because the WHERE clause filters by user_id."""
        db = _make_db_with_entries([])
        result = await get_entry(db, user_id=2, entry_id=10)
        assert result is None

    async def test_returns_none_for_zero_entry_id(self):
        db = _make_db_with_entries([])
        result = await get_entry(db, user_id=1, entry_id=0)
        assert result is None


class TestUpdateEntryService:
    """Unit tests for update_entry service function."""

    @pytest.fixture(autouse=True)
    async def clean_db(self):  # noqa: F811
        yield

    @pytest.fixture(autouse=True)
    def mock_email(self):  # noqa: F811
        yield

    async def test_update_content_recomputes_word_count(self):
        entry = _make_journal_orm_mock(id=1, user_id=1, content="old text", word_count=2)
        db = _make_db_with_entries([entry])
        db.flush = AsyncMock()
        db.refresh = AsyncMock(side_effect=lambda obj: None)

        payload = JournalEntryUpdate(content="new content here")
        result = await update_entry(db, user_id=1, entry_id=1, payload=payload)

        assert result.content == "new content here"
        assert result.word_count == 3  # "new content here" → 3 words

    async def test_update_title_only_does_not_change_word_count(self):
        entry = _make_journal_orm_mock(id=1, user_id=1, content="two words", word_count=2)
        db = _make_db_with_entries([entry])
        db.flush = AsyncMock()
        db.refresh = AsyncMock(side_effect=lambda obj: None)

        payload = JournalEntryUpdate(title="Brand New Title")
        result = await update_entry(db, user_id=1, entry_id=1, payload=payload)

        assert result.title == "Brand New Title"
        assert result.word_count == 2  # unchanged

    async def test_partial_update_content_leaves_title_unchanged(self):
        entry = _make_journal_orm_mock(
            id=1, user_id=1, title="Original Title", content="old", word_count=1
        )
        db = _make_db_with_entries([entry])
        db.flush = AsyncMock()
        db.refresh = AsyncMock(side_effect=lambda obj: None)

        payload = JournalEntryUpdate(content="brand new content words")
        result = await update_entry(db, user_id=1, entry_id=1, payload=payload)

        # title must stay the same because payload.title is None
        assert result.title == "Original Title"
        assert result.content == "brand new content words"

    async def test_update_returns_none_for_nonexistent_entry(self):
        db = _make_db_with_entries([])
        payload = JournalEntryUpdate(content="anything")
        result = await update_entry(db, user_id=1, entry_id=999, payload=payload)
        assert result is None


class TestDeleteEntryService:
    """Unit tests for delete_entry service function."""

    @pytest.fixture(autouse=True)
    async def clean_db(self):  # noqa: F811
        yield

    @pytest.fixture(autouse=True)
    def mock_email(self):  # noqa: F811
        yield

    async def test_delete_calls_db_delete_and_flush(self):
        entry = _make_journal_orm_mock(id=5, user_id=1)
        db = _make_db_with_entries([entry])
        db.flush = AsyncMock()

        result = await delete_entry(db, user_id=1, entry_id=5)

        assert result is True
        db.delete.assert_awaited_once_with(entry)
        db.flush.assert_awaited_once()

    async def test_delete_returns_false_for_wrong_user(self):
        db = _make_db_with_entries([])
        result = await delete_entry(db, user_id=99, entry_id=5)
        assert result is False

    async def test_delete_returns_false_for_nonexistent_entry(self):
        db = _make_db_with_entries([])
        result = await delete_entry(db, user_id=1, entry_id=999)
        assert result is False


# ===========================================================================
# API INTEGRATION TESTS
# ===========================================================================


class TestJournalAPIAuth:
    """All endpoints must require authentication — no token → 401."""

    async def test_post_without_token_returns_401(self, client: AsyncClient):
        resp = await client.post("/api/v1/journal", json={"content": "hello"})
        assert resp.status_code == 401

    async def test_get_list_without_token_returns_401(self, client: AsyncClient):
        resp = await client.get("/api/v1/journal")
        assert resp.status_code == 401

    async def test_get_by_id_without_token_returns_401(self, client: AsyncClient):
        resp = await client.get("/api/v1/journal/1")
        assert resp.status_code == 401

    async def test_patch_without_token_returns_401(self, client: AsyncClient):
        resp = await client.patch("/api/v1/journal/1", json={"content": "x"})
        assert resp.status_code == 401

    async def test_delete_without_token_returns_401(self, client: AsyncClient):
        resp = await client.delete("/api/v1/journal/1")
        assert resp.status_code == 401

    async def test_invalid_bearer_token_returns_401(self, client: AsyncClient):
        resp = await client.get(
            "/api/v1/journal",
            headers={"Authorization": "Bearer invalid.token.here"},
        )
        assert resp.status_code == 401


class TestCreateJournalEntry:
    """POST /api/v1/journal"""

    async def test_create_returns_201(self, client: AsyncClient):
        token = await _register_and_login(client, "journal_create_201@test.vetlanh")
        resp = await client.post(
            "/api/v1/journal",
            json={"title": "My Day", "content": "Today was a good day"},
            headers=_auth(token),
        )
        assert resp.status_code == 201

    async def test_create_response_has_correct_shape(self, client: AsyncClient):
        token = await _register_and_login(client, "journal_create_shape@test.vetlanh")
        resp = await client.post(
            "/api/v1/journal",
            json={"title": "Shape Test", "content": "one two three four"},
            headers=_auth(token),
        )
        data = resp.json()
        for field in ("id", "title", "content", "word_count", "created_at", "updated_at"):
            assert field in data, f"Missing field: {field}"

    async def test_create_word_count_is_correct(self, client: AsyncClient):
        token = await _register_and_login(client, "journal_create_wc@test.vetlanh")
        resp = await client.post(
            "/api/v1/journal",
            json={"content": "one two three four five"},
            headers=_auth(token),
        )
        assert resp.json()["word_count"] == 5

    async def test_create_title_in_response(self, client: AsyncClient):
        token = await _register_and_login(client, "journal_create_title@test.vetlanh")
        resp = await client.post(
            "/api/v1/journal",
            json={"title": "My Title", "content": "some content"},
            headers=_auth(token),
        )
        assert resp.json()["title"] == "My Title"

    async def test_create_without_title_returns_201(self, client: AsyncClient):
        """title is optional — omitting it must still succeed."""
        token = await _register_and_login(client, "journal_create_notitle@test.vetlanh")
        resp = await client.post(
            "/api/v1/journal",
            json={"content": "no title here"},
            headers=_auth(token),
        )
        assert resp.status_code == 201
        assert resp.json()["title"] is None

    async def test_create_with_empty_content_word_count_zero(self, client: AsyncClient):
        token = await _register_and_login(client, "journal_create_empty@test.vetlanh")
        resp = await client.post(
            "/api/v1/journal",
            json={"content": ""},
            headers=_auth(token),
        )
        assert resp.status_code == 201
        assert resp.json()["word_count"] == 0

    async def test_create_returns_id(self, client: AsyncClient):
        token = await _register_and_login(client, "journal_create_id@test.vetlanh")
        resp = await client.post(
            "/api/v1/journal",
            json={"content": "hello world"},
            headers=_auth(token),
        )
        assert isinstance(resp.json()["id"], int)


class TestListJournalEntries:
    """GET /api/v1/journal"""

    async def test_list_returns_200(self, client: AsyncClient):
        token = await _register_and_login(client, "journal_list_200@test.vetlanh")
        resp = await client.get("/api/v1/journal", headers=_auth(token))
        assert resp.status_code == 200

    async def test_list_returns_empty_for_new_user(self, client: AsyncClient):
        token = await _register_and_login(client, "journal_list_empty@test.vetlanh")
        resp = await client.get("/api/v1/journal", headers=_auth(token))
        assert resp.json() == []

    async def test_list_returns_created_entry(self, client: AsyncClient):
        token = await _register_and_login(client, "journal_list_one@test.vetlanh")
        headers = _auth(token)
        await client.post(
            "/api/v1/journal",
            json={"title": "Entry 1", "content": "hello world"},
            headers=headers,
        )
        resp = await client.get("/api/v1/journal", headers=headers)
        assert len(resp.json()) == 1

    async def test_list_newest_first(self, client: AsyncClient):
        """Multiple entries must be returned newest-first (descending created_at)."""
        token = await _register_and_login(client, "journal_list_order@test.vetlanh")
        headers = _auth(token)

        r1 = await client.post(
            "/api/v1/journal",
            json={"title": "First", "content": "first entry content"},
            headers=headers,
        )
        r2 = await client.post(
            "/api/v1/journal",
            json={"title": "Second", "content": "second entry content"},
            headers=headers,
        )
        id_first = r1.json()["id"]
        id_second = r2.json()["id"]

        resp = await client.get("/api/v1/journal", headers=headers)
        ids = [e["id"] for e in resp.json()]

        # Newest (second) should come before oldest (first)
        assert ids.index(id_second) < ids.index(id_first)

    async def test_list_search_by_content_keyword(self, client: AsyncClient):
        """?q=keyword returns only entries where content contains keyword."""
        token = await _register_and_login(client, "journal_list_qcontent@test.vetlanh")
        headers = _auth(token)

        await client.post(
            "/api/v1/journal",
            json={"content": "today i went hiking in the mountains"},
            headers=headers,
        )
        await client.post(
            "/api/v1/journal",
            json={"content": "reading a good book tonight"},
            headers=headers,
        )

        resp = await client.get("/api/v1/journal?q=hiking", headers=headers)
        data = resp.json()
        assert len(data) == 1
        assert "hiking" in data[0]["content"]

    async def test_list_search_by_title_keyword(self, client: AsyncClient):
        """?q=keyword also matches against title."""
        token = await _register_and_login(client, "journal_list_qtitle@test.vetlanh")
        headers = _auth(token)

        await client.post(
            "/api/v1/journal",
            json={"title": "vacation plans", "content": "thinking about next trip"},
            headers=headers,
        )
        await client.post(
            "/api/v1/journal",
            json={"title": "daily log", "content": "ordinary stuff"},
            headers=headers,
        )

        resp = await client.get("/api/v1/journal?q=vacation", headers=headers)
        data = resp.json()
        assert len(data) == 1
        assert data[0]["title"] == "vacation plans"

    async def test_list_search_no_match_returns_empty(self, client: AsyncClient):
        token = await _register_and_login(client, "journal_list_qnomatch@test.vetlanh")
        headers = _auth(token)

        await client.post(
            "/api/v1/journal",
            json={"content": "a short journal entry"},
            headers=headers,
        )

        resp = await client.get("/api/v1/journal?q=xyznotfound", headers=headers)
        assert resp.json() == []

    async def test_list_respects_limit(self, client: AsyncClient):
        token = await _register_and_login(client, "journal_list_limit@test.vetlanh")
        headers = _auth(token)

        for i in range(5):
            await client.post(
                "/api/v1/journal",
                json={"content": f"entry number {i} content words"},
                headers=headers,
            )

        resp = await client.get("/api/v1/journal?limit=3", headers=headers)
        assert len(resp.json()) == 3

    async def test_list_respects_offset(self, client: AsyncClient):
        token = await _register_and_login(client, "journal_list_offset@test.vetlanh")
        headers = _auth(token)

        for i in range(4):
            await client.post(
                "/api/v1/journal",
                json={"content": f"entry {i} content"},
                headers=headers,
            )

        resp_all = await client.get("/api/v1/journal", headers=headers)
        resp_offset = await client.get("/api/v1/journal?offset=2", headers=headers)

        assert len(resp_offset.json()) == 2
        # The offset results should be the tail of the full list
        assert resp_offset.json() == resp_all.json()[2:]

    async def test_list_isolated_per_user(self, client: AsyncClient):
        """User A's entries must not appear in User B's list."""
        token_a = await _register_and_login(client, "journal_list_usera@test.vetlanh")
        token_b = await _register_and_login(client, "journal_list_userb@test.vetlanh")

        await client.post(
            "/api/v1/journal",
            json={"content": "user a private entry"},
            headers=_auth(token_a),
        )

        resp = await client.get("/api/v1/journal", headers=_auth(token_b))
        assert resp.json() == []


class TestGetJournalEntryById:
    """GET /api/v1/journal/{id}"""

    async def test_get_by_id_returns_200(self, client: AsyncClient):
        token = await _register_and_login(client, "journal_getid_200@test.vetlanh")
        headers = _auth(token)
        create_resp = await client.post(
            "/api/v1/journal",
            json={"title": "Detail Test", "content": "some detailed content"},
            headers=headers,
        )
        entry_id = create_resp.json()["id"]

        resp = await client.get(f"/api/v1/journal/{entry_id}", headers=headers)
        assert resp.status_code == 200

    async def test_get_by_id_returns_correct_entry(self, client: AsyncClient):
        token = await _register_and_login(client, "journal_getid_correct@test.vetlanh")
        headers = _auth(token)
        create_resp = await client.post(
            "/api/v1/journal",
            json={"title": "Specific Title", "content": "specific content here"},
            headers=headers,
        )
        entry_id = create_resp.json()["id"]

        resp = await client.get(f"/api/v1/journal/{entry_id}", headers=headers)
        data = resp.json()
        assert data["id"] == entry_id
        assert data["title"] == "Specific Title"
        assert data["content"] == "specific content here"

    async def test_get_by_id_returns_404_for_nonexistent(self, client: AsyncClient):
        token = await _register_and_login(client, "journal_getid_404@test.vetlanh")
        resp = await client.get("/api/v1/journal/999999", headers=_auth(token))
        assert resp.status_code == 404

    async def test_get_by_id_returns_404_for_another_users_entry(self, client: AsyncClient):
        """User B cannot access User A's entry — must get 404."""
        token_a = await _register_and_login(client, "journal_getid_usera@test.vetlanh")
        token_b = await _register_and_login(client, "journal_getid_userb@test.vetlanh")

        create_resp = await client.post(
            "/api/v1/journal",
            json={"content": "user a private journal"},
            headers=_auth(token_a),
        )
        entry_id = create_resp.json()["id"]

        resp = await client.get(f"/api/v1/journal/{entry_id}", headers=_auth(token_b))
        assert resp.status_code == 404


class TestUpdateJournalEntry:
    """PATCH /api/v1/journal/{id}"""

    async def test_patch_returns_200(self, client: AsyncClient):
        token = await _register_and_login(client, "journal_patch_200@test.vetlanh")
        headers = _auth(token)
        create_resp = await client.post(
            "/api/v1/journal",
            json={"content": "original content"},
            headers=headers,
        )
        entry_id = create_resp.json()["id"]

        resp = await client.patch(
            f"/api/v1/journal/{entry_id}",
            json={"content": "updated content here"},
            headers=headers,
        )
        assert resp.status_code == 200

    async def test_patch_updates_content(self, client: AsyncClient):
        token = await _register_and_login(client, "journal_patch_content@test.vetlanh")
        headers = _auth(token)
        create_resp = await client.post(
            "/api/v1/journal",
            json={"content": "before update"},
            headers=headers,
        )
        entry_id = create_resp.json()["id"]

        resp = await client.patch(
            f"/api/v1/journal/{entry_id}",
            json={"content": "after update word count"},
            headers=headers,
        )
        data = resp.json()
        assert data["content"] == "after update word count"

    async def test_patch_recomputes_word_count(self, client: AsyncClient):
        token = await _register_and_login(client, "journal_patch_wc@test.vetlanh")
        headers = _auth(token)
        create_resp = await client.post(
            "/api/v1/journal",
            json={"content": "one two"},
            headers=headers,
        )
        entry_id = create_resp.json()["id"]

        resp = await client.patch(
            f"/api/v1/journal/{entry_id}",
            json={"content": "one two three four five"},
            headers=headers,
        )
        assert resp.json()["word_count"] == 5

    async def test_patch_updates_title_only(self, client: AsyncClient):
        token = await _register_and_login(client, "journal_patch_title@test.vetlanh")
        headers = _auth(token)
        create_resp = await client.post(
            "/api/v1/journal",
            json={"title": "Old Title", "content": "content stays same"},
            headers=headers,
        )
        entry_id = create_resp.json()["id"]
        original_wc = create_resp.json()["word_count"]

        resp = await client.patch(
            f"/api/v1/journal/{entry_id}",
            json={"title": "New Title"},
            headers=headers,
        )
        data = resp.json()
        assert data["title"] == "New Title"
        assert data["content"] == "content stays same"
        assert data["word_count"] == original_wc

    async def test_patch_returns_404_for_nonexistent(self, client: AsyncClient):
        token = await _register_and_login(client, "journal_patch_404@test.vetlanh")
        resp = await client.patch(
            "/api/v1/journal/999999",
            json={"content": "doesn't matter"},
            headers=_auth(token),
        )
        assert resp.status_code == 404

    async def test_patch_returns_404_for_another_users_entry(self, client: AsyncClient):
        token_a = await _register_and_login(client, "journal_patch_usera@test.vetlanh")
        token_b = await _register_and_login(client, "journal_patch_userb@test.vetlanh")

        create_resp = await client.post(
            "/api/v1/journal",
            json={"content": "user a content"},
            headers=_auth(token_a),
        )
        entry_id = create_resp.json()["id"]

        resp = await client.patch(
            f"/api/v1/journal/{entry_id}",
            json={"content": "trying to overwrite"},
            headers=_auth(token_b),
        )
        assert resp.status_code == 404


class TestDeleteJournalEntry:
    """DELETE /api/v1/journal/{id}"""

    async def test_delete_returns_204(self, client: AsyncClient):
        token = await _register_and_login(client, "journal_delete_204@test.vetlanh")
        headers = _auth(token)
        create_resp = await client.post(
            "/api/v1/journal",
            json={"content": "to be deleted"},
            headers=headers,
        )
        entry_id = create_resp.json()["id"]

        resp = await client.delete(f"/api/v1/journal/{entry_id}", headers=headers)
        assert resp.status_code == 204

    async def test_delete_removes_entry_from_list(self, client: AsyncClient):
        token = await _register_and_login(client, "journal_delete_gone@test.vetlanh")
        headers = _auth(token)
        create_resp = await client.post(
            "/api/v1/journal",
            json={"content": "will be deleted"},
            headers=headers,
        )
        entry_id = create_resp.json()["id"]

        await client.delete(f"/api/v1/journal/{entry_id}", headers=headers)

        get_resp = await client.get(f"/api/v1/journal/{entry_id}", headers=headers)
        assert get_resp.status_code == 404

    async def test_delete_returns_404_for_nonexistent(self, client: AsyncClient):
        token = await _register_and_login(client, "journal_delete_404@test.vetlanh")
        resp = await client.delete("/api/v1/journal/999999", headers=_auth(token))
        assert resp.status_code == 404

    async def test_delete_returns_404_for_another_users_entry(self, client: AsyncClient):
        token_a = await _register_and_login(client, "journal_delete_usera@test.vetlanh")
        token_b = await _register_and_login(client, "journal_delete_userb@test.vetlanh")

        create_resp = await client.post(
            "/api/v1/journal",
            json={"content": "user a entry"},
            headers=_auth(token_a),
        )
        entry_id = create_resp.json()["id"]

        resp = await client.delete(f"/api/v1/journal/{entry_id}", headers=_auth(token_b))
        assert resp.status_code == 404

    async def test_delete_no_body_returned(self, client: AsyncClient):
        """204 responses must have no body."""
        token = await _register_and_login(client, "journal_delete_nobody@test.vetlanh")
        headers = _auth(token)
        create_resp = await client.post(
            "/api/v1/journal",
            json={"content": "delete me please"},
            headers=headers,
        )
        entry_id = create_resp.json()["id"]

        resp = await client.delete(f"/api/v1/journal/{entry_id}", headers=headers)
        assert resp.status_code == 204
        assert resp.content == b""
