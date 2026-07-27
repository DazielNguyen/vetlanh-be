"""Integration tests for the Feedback API (docs/feedback-api.md)."""

import unittest.mock as mock

import pytest
from httpx import AsyncClient

ADMIN_USERNAME = "duy1"
ADMIN_PASSWORD = "Admin1234!"

VALID_PAYLOAD = {
    "rating": 4,
    "categories": ["interface", "audio"],
    "positive_comment": "Giao diện dễ chịu.",
    "improvement_comment": "Player che nội dung trên màn hình nhỏ.",
    "allow_contact": True,
    "source_page": "/services/settings",
    "app_version": "1.0.0",
}


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


async def _login_admin(client: AsyncClient) -> str:
    r = await client.post(
        "/api/v1/auth/login-username",
        json={"username": ADMIN_USERNAME, "password": ADMIN_PASSWORD},
    )
    assert r.status_code == 200, f"Admin login failed [{r.status_code}]: {r.text}"
    return r.json()["access_token"]


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


class TestCreateFeedback:
    async def test_creates_feedback_and_returns_formatted_id(self, client: AsyncClient):
        token = await _register_and_login(client, "fb-create@test.vetlanh")

        resp = await client.post("/api/v1/feedback", json=VALID_PAYLOAD, headers=_auth(token))

        assert resp.status_code == 201, resp.text
        body = resp.json()
        assert body["id"].startswith("fdb_")
        assert body["rating"] == 4
        assert body["categories"] == ["interface", "audio"]
        assert body["status"] == "new"
        assert body["created_at"]

    async def test_requires_authentication(self, client: AsyncClient):
        resp = await client.post("/api/v1/feedback", json=VALID_PAYLOAD)
        assert resp.status_code == 401

    async def test_rejects_rating_out_of_range(self, client: AsyncClient):
        token = await _register_and_login(client, "fb-badrating@test.vetlanh")
        payload = {**VALID_PAYLOAD, "rating": 6}
        resp = await client.post("/api/v1/feedback", json=payload, headers=_auth(token))
        assert resp.status_code == 422

    async def test_rejects_duplicate_categories(self, client: AsyncClient):
        token = await _register_and_login(client, "fb-dupcat@test.vetlanh")
        payload = {**VALID_PAYLOAD, "categories": ["audio", "audio"]}
        resp = await client.post("/api/v1/feedback", json=payload, headers=_auth(token))
        assert resp.status_code == 422

    async def test_rejects_full_url_as_source_page(self, client: AsyncClient):
        token = await _register_and_login(client, "fb-url@test.vetlanh")
        payload = {**VALID_PAYLOAD, "source_page": "https://evil.example/settings?token=abc"}
        resp = await client.post("/api/v1/feedback", json=payload, headers=_auth(token))
        assert resp.status_code == 422

    async def test_rejects_protocol_relative_url_as_source_page(self, client: AsyncClient):
        token = await _register_and_login(client, "fb-protorel@test.vetlanh")
        payload = {**VALID_PAYLOAD, "source_page": "//evil.example/settings?token=abc"}
        resp = await client.post("/api/v1/feedback", json=payload, headers=_auth(token))
        assert resp.status_code == 422

    async def test_ignores_client_supplied_identity_and_uses_token_user(self, client: AsyncClient):
        """Backend must derive user_id from the token, never trust FE-supplied fields."""
        token = await _register_and_login(client, "fb-identity@test.vetlanh")
        payload = {**VALID_PAYLOAD, "user_id": 999999, "email": "spoofed@evil.example"}

        resp = await client.post("/api/v1/feedback", json=payload, headers=_auth(token))
        assert resp.status_code == 201, resp.text

        admin_token = await _login_admin(client)
        listed = await client.get("/api/v1/admin/feedback", headers=_auth(admin_token))
        row = next(i for i in listed.json()["items"] if i["id"] == resp.json()["id"])
        assert row["user"]["email"] == "fb-identity@test.vetlanh"

    async def test_rate_limit_blocks_sixth_submission_within_an_hour(self, client: AsyncClient):
        token = await _register_and_login(client, "fb-ratelimit@test.vetlanh")
        for _ in range(5):
            resp = await client.post("/api/v1/feedback", json=VALID_PAYLOAD, headers=_auth(token))
            assert resp.status_code == 201, resp.text

        resp = await client.post("/api/v1/feedback", json=VALID_PAYLOAD, headers=_auth(token))
        assert resp.status_code == 429


class TestAdminFeedbackAccess:
    async def test_non_admin_cannot_list_feedback(self, client: AsyncClient):
        token = await _register_and_login(client, "fb-notadmin@test.vetlanh")
        resp = await client.get("/api/v1/admin/feedback", headers=_auth(token))
        assert resp.status_code == 403

    async def test_unauthenticated_cannot_list_feedback(self, client: AsyncClient):
        resp = await client.get("/api/v1/admin/feedback")
        assert resp.status_code == 401


class TestAdminFeedbackList:
    async def test_lists_and_filters_by_status_and_rating(self, client: AsyncClient):
        token = await _register_and_login(client, "fb-list@test.vetlanh")
        await client.post("/api/v1/feedback", json={**VALID_PAYLOAD, "rating": 5}, headers=_auth(token))
        await client.post("/api/v1/feedback", json={**VALID_PAYLOAD, "rating": 1}, headers=_auth(token))

        admin_token = await _login_admin(client)
        resp = await client.get(
            "/api/v1/admin/feedback",
            params={"rating": 5, "search": "fb-list"},
            headers=_auth(admin_token),
        )
        assert resp.status_code == 200, resp.text
        items = resp.json()["items"]
        assert len(items) >= 1
        assert all(i["rating"] == 5 for i in items)

    async def test_filters_by_subscription_status(self, client: AsyncClient):
        token = await _register_and_login(client, "fb-substatus@test.vetlanh")
        await client.post("/api/v1/feedback", json=VALID_PAYLOAD, headers=_auth(token))

        admin_token = await _login_admin(client)
        resp = await client.get(
            "/api/v1/admin/feedback",
            params={"subscription_status": "none", "search": "fb-substatus"},
            headers=_auth(admin_token),
        )
        assert resp.status_code == 200, resp.text
        assert len(resp.json()["items"]) == 1
        assert resp.json()["items"][0]["user"]["subscription_status"] == "none"

    async def test_search_matches_email(self, client: AsyncClient):
        token = await _register_and_login(client, "fb-searchmatch@test.vetlanh")
        await client.post("/api/v1/feedback", json=VALID_PAYLOAD, headers=_auth(token))

        admin_token = await _login_admin(client)
        resp = await client.get(
            "/api/v1/admin/feedback",
            params={"search": "fb-searchmatch"},
            headers=_auth(admin_token),
        )
        assert resp.status_code == 200, resp.text
        assert len(resp.json()["items"]) == 1


class TestAdminFeedbackStats:
    async def test_returns_rating_distribution_and_totals(self, client: AsyncClient):
        token = await _register_and_login(client, "fb-stats@test.vetlanh")
        await client.post("/api/v1/feedback", json={**VALID_PAYLOAD, "rating": 5}, headers=_auth(token))

        admin_token = await _login_admin(client)
        resp = await client.get("/api/v1/admin/feedback/stats", headers=_auth(admin_token))
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["total"] >= 1
        assert body["rating_distribution"]["5"] >= 1
        assert isinstance(body["top_categories"], list)


class TestAdminFeedbackDetailAndUpdate:
    async def test_detail_returns_404_for_unknown_id(self, client: AsyncClient):
        admin_token = await _login_admin(client)
        resp = await client.get("/api/v1/admin/feedback/fdb_999999999", headers=_auth(admin_token))
        assert resp.status_code == 404

    async def test_update_status_writes_audit_trail_and_is_reflected_in_detail(self, client: AsyncClient):
        token = await _register_and_login(client, "fb-update@test.vetlanh")
        create_resp = await client.post("/api/v1/feedback", json=VALID_PAYLOAD, headers=_auth(token))
        feedback_id = create_resp.json()["id"]

        admin_token = await _login_admin(client)
        resp = await client.patch(
            f"/api/v1/admin/feedback/{feedback_id}",
            json={"status": "planned", "internal_note": "Đưa vào sprint tới."},
            headers=_auth(admin_token),
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["status"] == "planned"
        assert resp.json()["internal_note"] == "Đưa vào sprint tới."

        detail = await client.get(f"/api/v1/admin/feedback/{feedback_id}", headers=_auth(admin_token))
        assert detail.json()["status"] == "planned"

    async def test_dismiss_without_internal_note_is_rejected(self, client: AsyncClient):
        token = await _register_and_login(client, "fb-dismiss@test.vetlanh")
        create_resp = await client.post("/api/v1/feedback", json=VALID_PAYLOAD, headers=_auth(token))
        feedback_id = create_resp.json()["id"]

        admin_token = await _login_admin(client)
        resp = await client.patch(
            f"/api/v1/admin/feedback/{feedback_id}",
            json={"status": "dismissed"},
            headers=_auth(admin_token),
        )
        assert resp.status_code == 422

    async def test_explicit_null_internal_note_clears_previous_note(self, client: AsyncClient):
        token = await _register_and_login(client, "fb-clearnote@test.vetlanh")
        create_resp = await client.post("/api/v1/feedback", json=VALID_PAYLOAD, headers=_auth(token))
        feedback_id = create_resp.json()["id"]

        admin_token = await _login_admin(client)
        await client.patch(
            f"/api/v1/admin/feedback/{feedback_id}",
            json={"internal_note": "Ghi chú tạm thời."},
            headers=_auth(admin_token),
        )

        resp = await client.patch(
            f"/api/v1/admin/feedback/{feedback_id}",
            json={"internal_note": None},
            headers=_auth(admin_token),
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["internal_note"] is None

    async def test_dismiss_with_internal_note_succeeds(self, client: AsyncClient):
        token = await _register_and_login(client, "fb-dismissok@test.vetlanh")
        create_resp = await client.post("/api/v1/feedback", json=VALID_PAYLOAD, headers=_auth(token))
        feedback_id = create_resp.json()["id"]

        admin_token = await _login_admin(client)
        resp = await client.patch(
            f"/api/v1/admin/feedback/{feedback_id}",
            json={"status": "dismissed", "internal_note": "Không phù hợp lộ trình hiện tại."},
            headers=_auth(admin_token),
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["status"] == "dismissed"
