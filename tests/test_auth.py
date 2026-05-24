"""
Integration tests for authentication endpoints.

Uses httpx.AsyncClient in-process — no real server, but real DB transactions.
The `client` and `clean_db` fixtures come from conftest.py.
"""

import pytest
from httpx import AsyncClient


# Helper so tests read like plain English
def reg_body(email: str, pw: str = "securepass1") -> dict:
    return {"email": email, "password": pw}


class TestRegister:
    async def test_short_password_returns_422(self, client: AsyncClient):
        resp = await client.post("/api/v1/auth/register", json=reg_body("a@test.vetlanh", "short"))
        assert resp.status_code == 422

    async def test_success_returns_201_and_unverified(self, client: AsyncClient):
        resp = await client.post("/api/v1/auth/register", json=reg_body("new@test.vetlanh"))
        assert resp.status_code == 201
        body = resp.json()
        assert body["email"] == "new@test.vetlanh"
        assert body["is_verified"] is False

    async def test_duplicate_email_returns_409(self, client: AsyncClient):
        payload = reg_body("dup@test.vetlanh")
        await client.post("/api/v1/auth/register", json=payload)
        resp = await client.post("/api/v1/auth/register", json=payload)
        assert resp.status_code == 409

    async def test_sends_verification_email(self, client: AsyncClient, mock_email):
        await client.post("/api/v1/auth/register", json=reg_body("email@test.vetlanh"))
        mock_email.assert_called_once()
        # First arg to send_verification_email is the recipient email
        assert mock_email.call_args.args[0] == "email@test.vetlanh"


class TestLogin:
    async def test_unverified_user_returns_403(self, client: AsyncClient):
        await client.post("/api/v1/auth/register", json=reg_body("unverified@test.vetlanh"))
        resp = await client.post("/api/v1/auth/login", json=reg_body("unverified@test.vetlanh"))
        assert resp.status_code == 403
        assert "verify" in resp.json()["detail"].lower()

    async def test_wrong_credentials_returns_401(self, client: AsyncClient):
        resp = await client.post(
            "/api/v1/auth/login",
            json=reg_body("ghost@test.vetlanh", "anypassword"),
        )
        assert resp.status_code == 401


class TestVerifyEmail:
    async def test_invalid_token_returns_400(self, client: AsyncClient):
        resp = await client.get("/api/v1/auth/verify?token=INVALID_TOKEN")
        assert resp.status_code == 400

    async def test_valid_token_marks_user_verified(self, client: AsyncClient):
        # Register → capture the token that would have been emailed
        mock_calls = []

        async def capture(*args, **kwargs):
            mock_calls.append(args)

        import unittest.mock as mock
        with mock.patch("app.api.v1.endpoints.auth.send_verification_email", side_effect=capture):
            await client.post("/api/v1/auth/register", json=reg_body("verify@test.vetlanh"))

        # The second arg is the token
        token = mock_calls[0][1]

        resp = await client.get(f"/api/v1/auth/verify?token={token}")
        assert resp.status_code == 200
        assert "verified" in resp.json()["message"].lower()


class TestResendVerification:
    async def test_unregistered_email_still_returns_200(self, client: AsyncClient):
        # Anti-enumeration: same response whether email exists or not
        resp = await client.post(
            "/api/v1/auth/resend-verification",
            json={"email": "ghost@test.vetlanh"},
        )
        assert resp.status_code == 200

    async def test_already_verified_returns_400(self, client: AsyncClient):
        # Register then manually verify via the token
        captured = []

        async def capture(*args, **kwargs):
            captured.append(args)

        import unittest.mock as mock
        with mock.patch("app.api.v1.endpoints.auth.send_verification_email", side_effect=capture):
            await client.post("/api/v1/auth/register", json=reg_body("resend@test.vetlanh"))

        token = captured[0][1]
        await client.get(f"/api/v1/auth/verify?token={token}")

        resp = await client.post(
            "/api/v1/auth/resend-verification",
            json={"email": "resend@test.vetlanh"},
        )
        assert resp.status_code == 400
