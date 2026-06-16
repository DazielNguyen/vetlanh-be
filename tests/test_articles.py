"""
Integration tests for the Articles ("Thư viện") CRUD endpoints — /api/v1/articles.

Covers:
  GET  /articles                       — published-only filter, category filter
  GET  /articles/{id}                  — happy path, 404
  POST /articles                       — success, 409 duplicate id, 422 invalid category,
                                          403 for non-admin
  PATCH /articles/{id}                 — partial update, publish auto-sets published_at
  POST /articles/{id}/upload-url       — admin only, 404 for missing article
  DELETE /articles/{id}                — admin only, 204, then 404 on re-fetch

Auth pattern mirrors tests/test_hub.py: register-username/login-username for a
regular user, and login-username as the seeded admin account "duy1" (whitelisted
via ADMIN_USERS, see app/core/seed.py) for admin-only endpoints.
"""

from datetime import datetime, timezone

import pytest
from httpx import AsyncClient
from sqlalchemy import text

from app.core.database import AsyncSessionLocal

ARTICLES_URL = "/api/v1/articles"

# Prefix for test-created articles and usernames so cleanup is precise.
_ARTICLE_ID_PREFIX = "test_article_"
_USERNAME_PREFIX = "art_"

ADMIN_USERNAME = "duy1"
ADMIN_PASSWORD = "Admin1234!"


@pytest.fixture(autouse=True)
async def clean_articles_and_users():
    """Delete test articles and test users before each test for isolation."""
    async with AsyncSessionLocal() as db:
        await db.execute(
            text("DELETE FROM articles WHERE id LIKE :prefix"),
            {"prefix": _ARTICLE_ID_PREFIX + "%"},
        )
        await db.execute(
            text("DELETE FROM users WHERE username LIKE :prefix"),
            {"prefix": _USERNAME_PREFIX + "%"},
        )
        await db.commit()
    yield


def _auth_header(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


async def _register_and_login(client: AsyncClient, username: str) -> str:
    """Register a regular (non-admin) username-only user and return an access token."""
    r = await client.post(
        "/api/v1/auth/register-username",
        json={"username": username, "password": "securepass1"},
    )
    assert r.status_code == 201, f"Registration failed [{r.status_code}]: {r.text}"
    r = await client.post(
        "/api/v1/auth/login-username",
        json={"username": username, "password": "securepass1"},
    )
    assert r.status_code == 200, f"Login failed [{r.status_code}]: {r.text}"
    return r.json()["access_token"]


async def _login_admin(client: AsyncClient) -> str:
    """Login as the seeded admin account (whitelisted in ADMIN_USERS)."""
    r = await client.post(
        "/api/v1/auth/login-username",
        json={"username": ADMIN_USERNAME, "password": ADMIN_PASSWORD},
    )
    assert r.status_code == 200, f"Admin login failed [{r.status_code}]: {r.text}"
    return r.json()["access_token"]


def _article_payload(article_id: str, **overrides) -> dict:
    payload = {
        "id": article_id,
        "title": "Hiểu về lo âu",
        "excerpt": "Một bài viết ngắn về lo âu",
        "content": "Nội dung đầy đủ của bài viết",
        "category": "psychology",
        "read_minutes": 5,
        "cover_url": None,
        "cloudinary_public_id": None,
        "is_published": False,
        "sort_order": 0,
    }
    payload.update(overrides)
    return payload


async def _create_article_via_api(
    client: AsyncClient, admin_token: str, article_id: str, **overrides
) -> dict:
    resp = await client.post(
        ARTICLES_URL,
        json=_article_payload(article_id, **overrides),
        headers=_auth_header(admin_token),
    )
    assert resp.status_code == 201, f"Create failed [{resp.status_code}]: {resp.text}"
    return resp.json()


# ===========================================================================
# GET /articles — list
# ===========================================================================

class TestListArticles:

    async def test_requires_auth(self, client: AsyncClient):
        resp = await client.get(ARTICLES_URL)
        assert resp.status_code in (401, 403)

    async def test_lists_only_published_articles(self, client: AsyncClient):
        admin_token = await _login_admin(client)
        user_token = await _register_and_login(client, f"{_USERNAME_PREFIX}list1")

        published = await _create_article_via_api(
            client, admin_token, f"{_ARTICLE_ID_PREFIX}pub1", is_published=True
        )
        await _create_article_via_api(
            client, admin_token, f"{_ARTICLE_ID_PREFIX}unpub1", is_published=False
        )

        resp = await client.get(ARTICLES_URL, headers=_auth_header(user_token))
        assert resp.status_code == 200
        ids = {a["id"] for a in resp.json()}
        assert published["id"] in ids
        assert f"{_ARTICLE_ID_PREFIX}unpub1" not in ids

    async def test_category_filter(self, client: AsyncClient):
        admin_token = await _login_admin(client)
        user_token = await _register_and_login(client, f"{_USERNAME_PREFIX}list2")

        await _create_article_via_api(
            client,
            admin_token,
            f"{_ARTICLE_ID_PREFIX}healing1",
            category="healing",
            is_published=True,
        )
        await _create_article_via_api(
            client,
            admin_token,
            f"{_ARTICLE_ID_PREFIX}lifestyle1",
            category="lifestyle",
            is_published=True,
        )

        resp = await client.get(
            ARTICLES_URL,
            params={"category": "healing"},
            headers=_auth_header(user_token),
        )
        assert resp.status_code == 200
        categories = {a["category"] for a in resp.json()}
        ids = {a["id"] for a in resp.json()}
        assert categories <= {"healing"}
        assert f"{_ARTICLE_ID_PREFIX}healing1" in ids
        assert f"{_ARTICLE_ID_PREFIX}lifestyle1" not in ids


# ===========================================================================
# GET /articles/{id}
# ===========================================================================

class TestGetArticle:

    async def test_get_existing_article(self, client: AsyncClient):
        admin_token = await _login_admin(client)
        user_token = await _register_and_login(client, f"{_USERNAME_PREFIX}get1")
        created = await _create_article_via_api(
            client, admin_token, f"{_ARTICLE_ID_PREFIX}get1"
        )

        resp = await client.get(
            f"{ARTICLES_URL}/{created['id']}", headers=_auth_header(user_token)
        )
        assert resp.status_code == 200
        assert resp.json()["id"] == created["id"]

    async def test_get_returns_unpublished_too(self, client: AsyncClient):
        """Single-article GET is not filtered by is_published, unlike list."""
        admin_token = await _login_admin(client)
        user_token = await _register_and_login(client, f"{_USERNAME_PREFIX}get2")
        created = await _create_article_via_api(
            client, admin_token, f"{_ARTICLE_ID_PREFIX}get2", is_published=False
        )

        resp = await client.get(
            f"{ARTICLES_URL}/{created['id']}", headers=_auth_header(user_token)
        )
        assert resp.status_code == 200
        assert resp.json()["is_published"] is False

    async def test_get_missing_article_404(self, client: AsyncClient):
        user_token = await _register_and_login(client, f"{_USERNAME_PREFIX}get3")
        resp = await client.get(
            f"{ARTICLES_URL}/{_ARTICLE_ID_PREFIX}does_not_exist",
            headers=_auth_header(user_token),
        )
        assert resp.status_code == 404


# ===========================================================================
# POST /articles — create
# ===========================================================================

class TestCreateArticle:

    async def test_create_success(self, client: AsyncClient):
        admin_token = await _login_admin(client)
        article_id = f"{_ARTICLE_ID_PREFIX}create1"
        resp = await client.post(
            ARTICLES_URL,
            json=_article_payload(article_id),
            headers=_auth_header(admin_token),
        )
        assert resp.status_code == 201
        body = resp.json()
        assert body["id"] == article_id
        assert body["category"] == "psychology"
        assert body["is_published"] is False
        assert body["published_at"] is None

    async def test_create_publish_sets_published_at(self, client: AsyncClient):
        admin_token = await _login_admin(client)
        article_id = f"{_ARTICLE_ID_PREFIX}create_pub"
        resp = await client.post(
            ARTICLES_URL,
            json=_article_payload(article_id, is_published=True),
            headers=_auth_header(admin_token),
        )
        assert resp.status_code == 201
        body = resp.json()
        assert body["is_published"] is True
        assert body["published_at"] is not None

    async def test_create_duplicate_id_returns_409(self, client: AsyncClient):
        admin_token = await _login_admin(client)
        article_id = f"{_ARTICLE_ID_PREFIX}dup1"
        await _create_article_via_api(client, admin_token, article_id)

        resp = await client.post(
            ARTICLES_URL,
            json=_article_payload(article_id),
            headers=_auth_header(admin_token),
        )
        assert resp.status_code == 409

    async def test_create_invalid_category_returns_422(self, client: AsyncClient):
        admin_token = await _login_admin(client)
        resp = await client.post(
            ARTICLES_URL,
            json=_article_payload(
                f"{_ARTICLE_ID_PREFIX}badcat", category="not_a_real_category"
            ),
            headers=_auth_header(admin_token),
        )
        assert resp.status_code == 422

    async def test_create_forbidden_for_non_admin(self, client: AsyncClient):
        user_token = await _register_and_login(client, f"{_USERNAME_PREFIX}create_na")
        resp = await client.post(
            ARTICLES_URL,
            json=_article_payload(f"{_ARTICLE_ID_PREFIX}forbidden1"),
            headers=_auth_header(user_token),
        )
        assert resp.status_code == 403

    async def test_create_requires_auth(self, client: AsyncClient):
        resp = await client.post(
            ARTICLES_URL, json=_article_payload(f"{_ARTICLE_ID_PREFIX}noauth")
        )
        assert resp.status_code in (401, 403)


# ===========================================================================
# PATCH /articles/{id} — update
# ===========================================================================

class TestUpdateArticle:

    async def test_partial_update(self, client: AsyncClient):
        admin_token = await _login_admin(client)
        created = await _create_article_via_api(
            client, admin_token, f"{_ARTICLE_ID_PREFIX}upd1"
        )

        resp = await client.patch(
            f"{ARTICLES_URL}/{created['id']}",
            json={"title": "Tiêu đề mới"},
            headers=_auth_header(admin_token),
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["title"] == "Tiêu đề mới"
        # Untouched fields remain unchanged.
        assert body["category"] == created["category"]
        assert body["excerpt"] == created["excerpt"]

    async def test_publish_transition_sets_published_at(self, client: AsyncClient):
        admin_token = await _login_admin(client)
        created = await _create_article_via_api(
            client, admin_token, f"{_ARTICLE_ID_PREFIX}upd_pub", is_published=False
        )
        assert created["published_at"] is None

        resp = await client.patch(
            f"{ARTICLES_URL}/{created['id']}",
            json={"is_published": True},
            headers=_auth_header(admin_token),
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["is_published"] is True
        assert body["published_at"] is not None

    async def test_update_invalid_category_returns_422(self, client: AsyncClient):
        admin_token = await _login_admin(client)
        created = await _create_article_via_api(
            client, admin_token, f"{_ARTICLE_ID_PREFIX}upd_badcat"
        )
        resp = await client.patch(
            f"{ARTICLES_URL}/{created['id']}",
            json={"category": "invalid_category"},
            headers=_auth_header(admin_token),
        )
        assert resp.status_code == 422

    async def test_update_missing_article_404(self, client: AsyncClient):
        admin_token = await _login_admin(client)
        resp = await client.patch(
            f"{ARTICLES_URL}/{_ARTICLE_ID_PREFIX}does_not_exist",
            json={"title": "x"},
            headers=_auth_header(admin_token),
        )
        assert resp.status_code == 404

    async def test_update_forbidden_for_non_admin(self, client: AsyncClient):
        admin_token = await _login_admin(client)
        user_token = await _register_and_login(client, f"{_USERNAME_PREFIX}upd_na")
        created = await _create_article_via_api(
            client, admin_token, f"{_ARTICLE_ID_PREFIX}upd_forbidden"
        )
        resp = await client.patch(
            f"{ARTICLES_URL}/{created['id']}",
            json={"title": "Hack"},
            headers=_auth_header(user_token),
        )
        assert resp.status_code == 403


# ===========================================================================
# POST /articles/{id}/upload-url
# ===========================================================================

class TestUploadUrl:

    async def test_upload_url_admin_only(self, client: AsyncClient):
        admin_token = await _login_admin(client)
        created = await _create_article_via_api(
            client, admin_token, f"{_ARTICLE_ID_PREFIX}upload1"
        )

        user_token = await _register_and_login(client, f"{_USERNAME_PREFIX}upload_na")
        resp = await client.post(
            f"{ARTICLES_URL}/{created['id']}/upload-url",
            headers=_auth_header(user_token),
        )
        assert resp.status_code == 403

    async def test_upload_url_success_for_admin(self, client: AsyncClient):
        admin_token = await _login_admin(client)
        created = await _create_article_via_api(
            client, admin_token, f"{_ARTICLE_ID_PREFIX}upload2"
        )

        resp = await client.post(
            f"{ARTICLES_URL}/{created['id']}/upload-url",
            headers=_auth_header(admin_token),
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["folder"] == "vetlanh/articles"
        assert "signature" in body
        assert "api_key" in body
        assert "upload_url" in body
        assert "image/upload" in body["upload_url"]

    async def test_upload_url_missing_article_404(self, client: AsyncClient):
        admin_token = await _login_admin(client)
        resp = await client.post(
            f"{ARTICLES_URL}/{_ARTICLE_ID_PREFIX}does_not_exist/upload-url",
            headers=_auth_header(admin_token),
        )
        assert resp.status_code == 404


# ===========================================================================
# DELETE /articles/{id}
# ===========================================================================

class TestDeleteArticle:

    async def test_delete_forbidden_for_non_admin(self, client: AsyncClient):
        admin_token = await _login_admin(client)
        created = await _create_article_via_api(
            client, admin_token, f"{_ARTICLE_ID_PREFIX}del_na"
        )
        user_token = await _register_and_login(client, f"{_USERNAME_PREFIX}del_na")

        resp = await client.delete(
            f"{ARTICLES_URL}/{created['id']}", headers=_auth_header(user_token)
        )
        assert resp.status_code == 403

    async def test_delete_success_then_404_on_refetch(self, client: AsyncClient):
        admin_token = await _login_admin(client)
        created = await _create_article_via_api(
            client, admin_token, f"{_ARTICLE_ID_PREFIX}del1"
        )

        resp = await client.delete(
            f"{ARTICLES_URL}/{created['id']}", headers=_auth_header(admin_token)
        )
        assert resp.status_code == 204

        resp2 = await client.get(
            f"{ARTICLES_URL}/{created['id']}", headers=_auth_header(admin_token)
        )
        assert resp2.status_code == 404

    async def test_delete_missing_article_404(self, client: AsyncClient):
        admin_token = await _login_admin(client)
        resp = await client.delete(
            f"{ARTICLES_URL}/{_ARTICLE_ID_PREFIX}does_not_exist",
            headers=_auth_header(admin_token),
        )
        assert resp.status_code == 404
