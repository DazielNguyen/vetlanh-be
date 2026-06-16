"""
Integration tests for GET /api/v1/users/me exposing subscription status.

Covers app/services/subscription.py::get_subscription_status logic as surfaced
through the /users/me endpoint:
- no subscriptions at all -> "none"
- active subscription with future expires_at -> "pro"
- active subscription with past expires_at -> "expired"
- only "pending" subscriptions (never granted) -> "none" (pending must not count)
"""

import uuid
from datetime import datetime, timedelta, timezone

import pytest
from httpx import AsyncClient
from sqlalchemy import text

from app.core.database import AsyncSessionLocal
from app.models.subscription import Subscription
from app.models.user import User

_USERNAME_PREFIX = "usersub_"


@pytest.fixture(autouse=True)
async def clean_subscriptions_and_users():
    async with AsyncSessionLocal() as db:
        await db.execute(
            text(
                "DELETE FROM subscriptions WHERE user_id IN "
                "(SELECT id FROM users WHERE username LIKE :prefix)"
            ),
            {"prefix": _USERNAME_PREFIX + "%"},
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


async def _get_user_id(username: str) -> int:
    async with AsyncSessionLocal() as db:
        row = (
            await db.execute(
                text("SELECT id FROM users WHERE username = :username"),
                {"username": username},
            )
        ).first()
    assert row is not None
    return row[0]


async def _insert_subscription(
    user_id: int,
    status: str,
    plan_name: str | None = None,
    expires_at: datetime | None = None,
    granted_at: datetime | None = None,
) -> None:
    async with AsyncSessionLocal() as db:
        sub = Subscription(
            id=uuid.uuid4(),
            user_id=user_id,
            status=status,
            plan_name=plan_name,
            expires_at=expires_at,
            granted_at=granted_at,
        )
        db.add(sub)
        await db.commit()


class TestSubscriptionStatusNone:

    async def test_brand_new_user_has_no_subscription_status_none(self, client: AsyncClient):
        username = f"{_USERNAME_PREFIX}none1"
        token = await _register_and_login(client, username)

        resp = await client.get("/api/v1/users/me", headers=_auth_header(token))
        assert resp.status_code == 200, f"/users/me failed [{resp.status_code}]: {resp.text}"

        body = resp.json()
        assert body["subscription_status"] == "none"
        assert body["subscription_plan"] is None
        assert body["subscription_expires_at"] is None

    async def test_only_pending_subscription_does_not_count_as_pro(self, client: AsyncClient):
        username = f"{_USERNAME_PREFIX}none2"
        token = await _register_and_login(client, username)
        user_id = await _get_user_id(username)

        future = datetime.now(timezone.utc) + timedelta(days=30)
        await _insert_subscription(
            user_id,
            status="pending",
            plan_name="monthly",
            expires_at=future,
            granted_at=None,
        )

        resp = await client.get("/api/v1/users/me", headers=_auth_header(token))
        assert resp.status_code == 200

        body = resp.json()
        assert body["subscription_status"] == "none"
        assert body["subscription_plan"] is None
        assert body["subscription_expires_at"] is None


class TestSubscriptionStatusPro:

    async def test_active_subscription_with_future_expiry_is_pro(self, client: AsyncClient):
        username = f"{_USERNAME_PREFIX}pro1"
        token = await _register_and_login(client, username)
        user_id = await _get_user_id(username)

        future = datetime.now(timezone.utc) + timedelta(days=30)
        granted = datetime.now(timezone.utc) - timedelta(days=1)
        await _insert_subscription(
            user_id,
            status="active",
            plan_name="monthly",
            expires_at=future,
            granted_at=granted,
        )

        resp = await client.get("/api/v1/users/me", headers=_auth_header(token))
        assert resp.status_code == 200

        body = resp.json()
        assert body["subscription_status"] == "pro"
        assert body["subscription_plan"] == "monthly"
        assert body["subscription_expires_at"] is not None
        returned = datetime.fromisoformat(body["subscription_expires_at"])
        if returned.tzinfo is None:
            returned = returned.replace(tzinfo=timezone.utc)
        assert abs((returned - future).total_seconds()) < 2


    async def test_two_active_rows_one_expired_one_valid_still_reports_pro(self, client: AsyncClient):
        """Regression guard: status must come from the conjunction query, not just
        the most-recently-granted active row — see app/services/subscription.py."""
        username = f"{_USERNAME_PREFIX}pro2"
        token = await _register_and_login(client, username)
        user_id = await _get_user_id(username)

        past = datetime.now(timezone.utc) - timedelta(days=1)
        future = datetime.now(timezone.utc) + timedelta(days=30)
        await _insert_subscription(
            user_id,
            status="active",
            plan_name="1thang",
            expires_at=past,
            granted_at=datetime.now(timezone.utc) - timedelta(days=40),
        )
        await _insert_subscription(
            user_id,
            status="active",
            plan_name="1nam",
            expires_at=future,
            granted_at=datetime.now(timezone.utc) - timedelta(days=1),
        )

        resp = await client.get("/api/v1/users/me", headers=_auth_header(token))
        assert resp.status_code == 200

        body = resp.json()
        assert body["subscription_status"] == "pro"
        assert body["subscription_plan"] == "1nam"


class TestSubscriptionStatusExpired:

    async def test_active_subscription_with_past_expiry_is_expired(self, client: AsyncClient):
        username = f"{_USERNAME_PREFIX}expired1"
        token = await _register_and_login(client, username)
        user_id = await _get_user_id(username)

        past = datetime.now(timezone.utc) - timedelta(days=1)
        granted = datetime.now(timezone.utc) - timedelta(days=40)
        await _insert_subscription(
            user_id,
            status="active",
            plan_name="1nam",
            expires_at=past,
            granted_at=granted,
        )

        resp = await client.get("/api/v1/users/me", headers=_auth_header(token))
        assert resp.status_code == 200

        body = resp.json()
        assert body["subscription_status"] == "expired"
        assert body["subscription_plan"] == "1nam"
        assert body["subscription_expires_at"] is not None
