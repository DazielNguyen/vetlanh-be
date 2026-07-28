"""
Integration tests for authentication endpoints.

Uses httpx.AsyncClient in-process — no real server, but real DB transactions.
The `client` and `clean_db` fixtures come from conftest.py.
"""

import asyncio

from httpx import AsyncClient
from sqlalchemy import select

from app.core.database import AsyncSessionLocal
from app.core.security import hash_password
from app.models.user import User


# Helper so tests read like plain English
def reg_body(email: str, pw: str = "securepass1") -> dict:
    return {"email": email, "password": pw}


class TestRegister:
    async def test_short_password_returns_422(self, client: AsyncClient):
        resp = await client.post("/api/v1/auth/register", json=reg_body("a@test.vetlanh", "short"))
        assert resp.status_code == 422

    async def test_success_returns_201_and_verified(self, client: AsyncClient):
        resp = await client.post("/api/v1/auth/register", json=reg_body("new@test.vetlanh"))
        assert resp.status_code == 201
        body = resp.json()
        assert body["email"] == "new@test.vetlanh"
        assert body["is_active"] is True
        assert body["is_verified"] is True

        async with AsyncSessionLocal() as db:
            user = (
                await db.execute(
                    select(User).where(User.email == "new@test.vetlanh")
                )
            ).scalar_one()
            assert user.verification_token is None
            assert user.verification_token_expires_at is None

    async def test_duplicate_email_returns_409(self, client: AsyncClient):
        payload = reg_body("dup@test.vetlanh")
        await client.post("/api/v1/auth/register", json=payload)
        resp = await client.post("/api/v1/auth/register", json=payload)
        assert resp.status_code == 409

    async def test_concurrent_duplicate_creates_one_user(self, client: AsyncClient):
        payload = reg_body("race@test.vetlanh")
        responses = await asyncio.gather(
            client.post("/api/v1/auth/register", json=payload),
            client.post("/api/v1/auth/register", json=payload),
        )
        assert sorted(response.status_code for response in responses) == [201, 409]

        async with AsyncSessionLocal() as db:
            users = (
                await db.execute(
                    select(User).where(User.email == "race@test.vetlanh")
                )
            ).scalars().all()
            assert len(users) == 1

    async def test_does_not_send_verification_email(self, client: AsyncClient, mock_email):
        await client.post("/api/v1/auth/register", json=reg_body("email@test.vetlanh"))
        mock_email.assert_not_called()


class TestLogin:
    async def test_new_user_can_login_immediately(self, client: AsyncClient):
        payload = reg_body("verified@test.vetlanh")
        await client.post("/api/v1/auth/register", json=payload)
        resp = await client.post("/api/v1/auth/login", json=payload)
        assert resp.status_code == 200
        assert resp.json()["access_token"]

    async def test_legacy_unverified_user_returns_403(self, client: AsyncClient):
        async with AsyncSessionLocal() as db:
            db.add(
                User(
                    email="unverified@test.vetlanh",
                    hashed_password=hash_password("securepass1"),
                    is_verified=False,
                )
            )
            await db.commit()

        resp = await client.post(
            "/api/v1/auth/login", json=reg_body("unverified@test.vetlanh")
        )
        assert resp.status_code == 403
        assert "verify" in resp.json()["detail"].lower()

    async def test_deactivated_user_returns_403(self, client: AsyncClient):
        payload = reg_body("locked@test.vetlanh")
        await client.post("/api/v1/auth/register", json=payload)
        async with AsyncSessionLocal() as db:
            user = (
                await db.execute(
                    select(User).where(User.email == "locked@test.vetlanh")
                )
            ).scalar_one()
            user.is_active = False
            await db.commit()

        resp = await client.post("/api/v1/auth/login", json=payload)
        assert resp.status_code == 403
        assert resp.json()["detail"] == "Account is deactivated"

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
        token = "legacy-verification-token"
        async with AsyncSessionLocal() as db:
            db.add(
                User(
                    email="verify@test.vetlanh",
                    hashed_password=hash_password("securepass1"),
                    is_verified=False,
                    verification_token=token,
                )
            )
            await db.commit()

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
        await client.post(
            "/api/v1/auth/register", json=reg_body("resend@test.vetlanh")
        )

        resp = await client.post(
            "/api/v1/auth/resend-verification",
            json={"email": "resend@test.vetlanh"},
        )
        assert resp.status_code == 400
