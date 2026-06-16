"""
Integration test for POST /api/v1/subscriptions/payment-notify.

Covers the bug fix where transfer_date was left NULL for this multipart flow
(unlike /subscriptions/pending, which receives transfer_date in the body),
causing the FE to render the epoch fallback (01/01/1970). The fix sets
transfer_date to the server's receipt time.
"""

from datetime import datetime, timezone

import pytest
from httpx import AsyncClient
from sqlalchemy import select, text
from unittest.mock import AsyncMock, patch

from app.core.database import AsyncSessionLocal
from app.models.subscription import Subscription

_USERNAME_PREFIX = "sub_"

ADMIN_USERNAME = "duy1"
ADMIN_PASSWORD = "Admin1234!"


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


async def _login_admin(client: AsyncClient) -> str:
    r = await client.post(
        "/api/v1/auth/login-username",
        json={"username": ADMIN_USERNAME, "password": ADMIN_PASSWORD},
    )
    assert r.status_code == 200, f"Admin login failed [{r.status_code}]: {r.text}"
    return r.json()["access_token"]


class TestPaymentNotifyTransferDate:

    async def test_transfer_date_is_populated_with_server_receipt_time(self, client: AsyncClient):
        token = await _register_and_login(client, f"{_USERNAME_PREFIX}user1")

        before = datetime.now(timezone.utc)
        with patch(
            "app.api.v1.endpoints.subscriptions.save_upload",
            new=AsyncMock(return_value="https://cdn.test/bill.png"),
        ):
            resp = await client.post(
                "/api/v1/subscriptions/payment-notify",
                data={"package_key": "monthly", "amount": "99000"},
                files={"bill_image": ("bill.png", b"fake-bytes", "image/png")},
                headers=_auth_header(token),
            )
        after = datetime.now(timezone.utc)

        assert resp.status_code == 201, f"payment-notify failed [{resp.status_code}]: {resp.text}"
        sub_id = resp.json()["id"]

        async with AsyncSessionLocal() as db:
            sub = (
                await db.execute(select(Subscription).where(Subscription.id == sub_id))
            ).scalar_one()

        assert sub.transfer_date is not None, "transfer_date must not be NULL — FE renders epoch (01/01/1970) for null"
        assert before <= sub.transfer_date <= after


class TestPaymentNotifyDurationMonths:
    """
    payment-notify only receives package_key, not duration_months — without a
    server-side package_key -> months mapping, sub.duration_months stayed NULL,
    and admin's "Duyệt" (grant) always failed with 422 since neither the grant
    body nor the stored row had a usable duration.
    """

    async def test_duration_months_is_derived_from_package_key(self, client: AsyncClient):
        token = await _register_and_login(client, f"{_USERNAME_PREFIX}user2")

        with patch(
            "app.api.v1.endpoints.subscriptions.save_upload",
            new=AsyncMock(return_value="https://cdn.test/bill.png"),
        ):
            resp = await client.post(
                "/api/v1/subscriptions/payment-notify",
                data={"package_key": "1nam", "amount": "599000"},
                files={"bill_image": ("bill.png", b"fake-bytes", "image/png")},
                headers=_auth_header(token),
            )
        assert resp.status_code == 201, f"payment-notify failed [{resp.status_code}]: {resp.text}"
        sub_id = resp.json()["id"]

        async with AsyncSessionLocal() as db:
            sub = (
                await db.execute(select(Subscription).where(Subscription.id == sub_id))
            ).scalar_one()
        assert sub.duration_months == 12

    async def test_grant_succeeds_without_admin_override_after_bill_upload_flow(self, client: AsyncClient):
        token = await _register_and_login(client, f"{_USERNAME_PREFIX}user3")

        with patch(
            "app.api.v1.endpoints.subscriptions.save_upload",
            new=AsyncMock(return_value="https://cdn.test/bill.png"),
        ):
            resp = await client.post(
                "/api/v1/subscriptions/payment-notify",
                data={"package_key": "1nam", "amount": "599000"},
                files={"bill_image": ("bill.png", b"fake-bytes", "image/png")},
                headers=_auth_header(token),
            )
        assert resp.status_code == 201
        sub_id = resp.json()["id"]

        admin_token = await _login_admin(client)
        grant_resp = await client.post(
            f"/api/v1/admin/subscriptions/{sub_id}/grant",
            json={},
            headers=_auth_header(admin_token),
        )
        assert grant_resp.status_code == 200, f"grant failed [{grant_resp.status_code}]: {grant_resp.text}"


class TestPendingListIncludesBillImageUrl:
    """
    The admin pending-list endpoint omitted bill_image_url even though the FE
    already renders it — admins had no way to view the uploaded bill on the FE
    (only via the email notification link).
    """

    async def test_pending_list_returns_bill_image_url(self, client: AsyncClient):
        token = await _register_and_login(client, f"{_USERNAME_PREFIX}user4")

        with patch(
            "app.api.v1.endpoints.subscriptions.save_upload",
            new=AsyncMock(return_value="https://res.cloudinary.com/test/bill.png"),
        ):
            resp = await client.post(
                "/api/v1/subscriptions/payment-notify",
                data={"package_key": "1nam", "amount": "599000"},
                files={"bill_image": ("bill.png", b"fake-bytes", "image/png")},
                headers=_auth_header(token),
            )
        assert resp.status_code == 201

        admin_token = await _login_admin(client)
        list_resp = await client.get(
            "/api/v1/admin/subscriptions/pending",
            headers=_auth_header(admin_token),
        )
        assert list_resp.status_code == 200
        rows = [r for r in list_resp.json() if r["id"] == resp.json()["id"]]
        assert len(rows) == 1
        assert rows[0]["bill_image_url"] == "https://res.cloudinary.com/test/bill.png"
