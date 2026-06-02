"""
Tests for US-030: Journal Entry Encryption.

Covers:
  - New journal entry content is readable via API (decrypt-on-read works)
  - Raw DB value is ciphertext, not plaintext (encrypt-on-write works)
  - Search by title still works after encryption
  - Search by content keyword no longer matches (content search dropped)
  - Existing CRUD tests unaffected (smoke-test create/update/delete)
"""

import unittest.mock as mock

import pytest
from httpx import AsyncClient
from sqlalchemy import text

from app.core.database import AsyncSessionLocal

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

TEST_DOMAIN = "test.vetlanh"


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


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestJournalEncryption:
    async def test_created_content_readable_via_api(self, client: AsyncClient):
        token = await _register_and_login(client, f"enc_read@{TEST_DOMAIN}")
        resp = await client.post(
            "/api/v1/journal",
            json={"title": "My Entry", "content": "Hello plaintext world"},
            headers=_auth(token),
        )
        assert resp.status_code == 201
        assert resp.json()["content"] == "Hello plaintext world"

    async def test_raw_db_value_is_ciphertext(self, client: AsyncClient):
        """The value stored in the DB column must not equal the plaintext."""
        token = await _register_and_login(client, f"enc_raw@{TEST_DOMAIN}")
        resp = await client.post(
            "/api/v1/journal",
            json={"title": "Raw Check", "content": "secret text here"},
            headers=_auth(token),
        )
        entry_id = resp.json()["id"]

        async with AsyncSessionLocal() as db:
            row = await db.execute(
                text("SELECT content FROM journal_entries WHERE id = :id"),
                {"id": entry_id},
            )
            raw = row.scalar_one()

        assert raw != "secret text here"
        assert raw.startswith("gAAAAA")  # Fernet token prefix

    async def test_read_back_after_create_matches_plaintext(self, client: AsyncClient):
        token = await _register_and_login(client, f"enc_rb@{TEST_DOMAIN}")
        await client.post(
            "/api/v1/journal",
            json={"title": "Roundtrip", "content": "roundtrip content"},
            headers=_auth(token),
        )
        list_resp = await client.get("/api/v1/journal", headers=_auth(token))
        assert list_resp.status_code == 200
        entry = list_resp.json()[0]
        assert entry["content"] == "roundtrip content"

    async def test_search_by_title_still_works(self, client: AsyncClient):
        token = await _register_and_login(client, f"enc_title@{TEST_DOMAIN}")
        await client.post(
            "/api/v1/journal",
            json={"title": "UniqueTitle123", "content": "some body text"},
            headers=_auth(token),
        )
        resp = await client.get("/api/v1/journal?q=UniqueTitle123", headers=_auth(token))
        assert resp.status_code == 200
        assert len(resp.json()) == 1
        assert resp.json()[0]["title"] == "UniqueTitle123"

    async def test_search_by_content_keyword_does_not_match(self, client: AsyncClient):
        """After encryption, content search must return no results for a content-only keyword."""
        token = await _register_and_login(client, f"enc_nosearch@{TEST_DOMAIN}")
        await client.post(
            "/api/v1/journal",
            json={"title": "Unrelated Title", "content": "xyzContentKeyword789"},
            headers=_auth(token),
        )
        resp = await client.get(
            "/api/v1/journal?q=xyzContentKeyword789", headers=_auth(token)
        )
        assert resp.status_code == 200
        assert resp.json() == []

    async def test_update_content_still_readable(self, client: AsyncClient):
        token = await _register_and_login(client, f"enc_update@{TEST_DOMAIN}")
        create_resp = await client.post(
            "/api/v1/journal",
            json={"title": "Update Test", "content": "original content"},
            headers=_auth(token),
        )
        entry_id = create_resp.json()["id"]

        await client.patch(
            f"/api/v1/journal/{entry_id}",
            json={"content": "updated content"},
            headers=_auth(token),
        )

        get_resp = await client.get(f"/api/v1/journal/{entry_id}", headers=_auth(token))
        assert get_resp.json()["content"] == "updated content"

    async def test_updated_raw_value_is_still_ciphertext(self, client: AsyncClient):
        token = await _register_and_login(client, f"enc_upraw@{TEST_DOMAIN}")
        create_resp = await client.post(
            "/api/v1/journal",
            json={"title": "Raw Update", "content": "original"},
            headers=_auth(token),
        )
        entry_id = create_resp.json()["id"]

        await client.patch(
            f"/api/v1/journal/{entry_id}",
            json={"content": "new plaintext"},
            headers=_auth(token),
        )

        async with AsyncSessionLocal() as db:
            row = await db.execute(
                text("SELECT content FROM journal_entries WHERE id = :id"),
                {"id": entry_id},
            )
            raw = row.scalar_one()

        assert raw != "new plaintext"
        assert raw.startswith("gAAAAA")

    async def test_empty_content_roundtrip(self, client: AsyncClient):
        token = await _register_and_login(client, f"enc_empty@{TEST_DOMAIN}")
        resp = await client.post(
            "/api/v1/journal",
            json={"title": "Empty Content", "content": ""},
            headers=_auth(token),
        )
        assert resp.status_code == 201
        assert resp.json()["content"] == ""
