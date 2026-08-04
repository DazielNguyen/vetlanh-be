"""Integration tests for the Admin Analytics API (docs/2026-08-04-be-analytics-events-contract.md)."""

from datetime import datetime, timedelta, timezone

from httpx import AsyncClient
from sqlalchemy import select

from app.core.database import AsyncSessionLocal
from app.models.subscription import Subscription
from app.models.telemetry import Event
from app.models.user import User

ADMIN_USERNAME = "duy1"
ADMIN_PASSWORD = "Admin1234!"


def _reg_body(email: str, pw: str = "securepass1") -> dict:
    return {"email": email, "password": pw}


async def _register(client: AsyncClient, email: str) -> int:
    resp = await client.post("/api/v1/auth/register", json=_reg_body(email))
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


async def _login_admin(client: AsyncClient) -> str:
    r = await client.post(
        "/api/v1/auth/login-username",
        json={"username": ADMIN_USERNAME, "password": ADMIN_PASSWORD},
    )
    assert r.status_code == 200, f"Admin login failed [{r.status_code}]: {r.text}"
    return r.json()["access_token"]


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


async def _grant_subscription(user_id: int) -> None:
    async with AsyncSessionLocal() as db:
        db.add(
            Subscription(
                user_id=user_id,
                status="active",
                granted_at=datetime.now(tz=timezone.utc),
                expires_at=datetime.now(tz=timezone.utc) + timedelta(days=30),
            )
        )
        await db.commit()


async def _pending_subscription(user_id: int) -> None:
    async with AsyncSessionLocal() as db:
        db.add(Subscription(user_id=user_id, status="pending"))
        await db.commit()


class TestConversionRate:
    async def test_counts_only_granted_subscriptions(self, client: AsyncClient):
        # The endpoint intentionally counts ALL users joined "today" (no domain
        # scoping — that's correct for a real admin report). Other test files
        # register users under domains clean_db doesn't scope to (e.g.
        # example.com), which can leak into "today"'s count across the full
        # suite. Baseline-delta avoids asserting an absolute count.
        today = datetime.now(tz=timezone.utc).date().isoformat()
        admin_token = await _login_admin(client)

        async def _rate() -> dict:
            resp = await client.get(
                "/api/v1/admin/analytics/conversion-rate",
                params={"joined_from": today, "joined_to": today},
                headers=_auth(admin_token),
            )
            assert resp.status_code == 200, resp.text
            return resp.json()

        baseline = await _rate()

        converted_id = await _register(client, "converted@test.vetlanh")
        pending_id = await _register(client, "pending@test.vetlanh")
        await _register(client, "plain@test.vetlanh")

        await _grant_subscription(converted_id)
        await _pending_subscription(pending_id)

        after = await _rate()
        assert after["joined_count"] == baseline["joined_count"] + 3
        assert after["converted_count"] == baseline["converted_count"] + 1

    async def test_empty_range_returns_zero_rate(self, client: AsyncClient):
        admin_token = await _login_admin(client)
        resp = await client.get(
            "/api/v1/admin/analytics/conversion-rate",
            params={"joined_from": "2000-01-01", "joined_to": "2000-01-02"},
            headers=_auth(admin_token),
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body == {"joined_count": 0, "converted_count": 0, "conversion_rate": 0.0}

    async def test_rejects_non_admin(self, client: AsyncClient):
        resp = await client.get(
            "/api/v1/admin/analytics/conversion-rate",
            params={"joined_from": "2026-01-01", "joined_to": "2026-01-02"},
        )
        assert resp.status_code == 401


async def _seed_events(rows: list[dict]) -> None:
    async with AsyncSessionLocal() as db:
        for row in rows:
            db.add(Event(**row))
        await db.commit()


class TestFeatureUsage:
    async def test_counts_events_by_type_in_range(self, client: AsyncClient):
        # Anchored far in the past so other tests' real-time event inserts never overlap this window.
        anchor = datetime(2020, 1, 15, tzinfo=timezone.utc)
        await _seed_events(
            [
                {"event_name": "chat_message_sent", "user_id": "u1", "event_metadata": {}, "created_at": anchor},
                {"event_name": "chat_message_sent", "user_id": "u2", "event_metadata": {}, "created_at": anchor},
                {"event_name": "mood_checkin_logged", "user_id": "u1", "event_metadata": {}, "created_at": anchor},
                # Outside the requested range — must not be counted.
                {
                    "event_name": "chat_message_sent",
                    "user_id": "u3",
                    "event_metadata": {},
                    "created_at": datetime(2020, 2, 1, tzinfo=timezone.utc),
                },
            ]
        )

        admin_token = await _login_admin(client)
        resp = await client.get(
            "/api/v1/admin/analytics/feature-usage",
            params={"from": "2020-01-01", "to": "2020-01-31"},
            headers=_auth(admin_token),
        )
        assert resp.status_code == 200, resp.text
        counts = {row["event_name"]: row["count"] for row in resp.json()}
        assert counts == {"chat_message_sent": 2, "mood_checkin_logged": 1}

    async def test_rejects_non_admin(self, client: AsyncClient):
        resp = await client.get(
            "/api/v1/admin/analytics/feature-usage",
            params={"from": "2020-01-01", "to": "2020-01-31"},
        )
        assert resp.status_code == 401


class TestMonthlyActiveUsers:
    async def test_page_view_only_user_excluded_real_action_user_included(self, client: AsyncClient):
        now = datetime.now(tz=timezone.utc)
        current_month_key = now.strftime("%Y-%m")

        async def _active_users_for_current_month(client: AsyncClient, admin_token: str) -> int:
            resp = await client.get(
                "/api/v1/admin/analytics/mau",
                params={"months": 1},
                headers=_auth(admin_token),
            )
            assert resp.status_code == 200, resp.text
            row = next(r for r in resp.json() if r["month"] == current_month_key)
            return row["active_users"]

        admin_token = await _login_admin(client)
        baseline = await _active_users_for_current_month(client, admin_token)

        page_view_only_user = "mau-test-page-view-only"
        active_user = "mau-test-active-user"
        await _seed_events(
            [
                {"event_name": "page_view", "user_id": page_view_only_user, "event_metadata": {}, "created_at": now},
                {"event_name": "exercise_played", "user_id": active_user, "event_metadata": {}, "created_at": now},
            ]
        )

        after = await _active_users_for_current_month(client, admin_token)
        assert after == baseline + 1

    async def test_returns_one_row_per_requested_month(self, client: AsyncClient):
        admin_token = await _login_admin(client)
        resp = await client.get(
            "/api/v1/admin/analytics/mau",
            params={"months": 6},
            headers=_auth(admin_token),
        )
        assert resp.status_code == 200, resp.text
        assert len(resp.json()) == 6

    async def test_null_user_id_events_never_counted(self, client: AsyncClient):
        now = datetime.now(tz=timezone.utc)
        current_month_key = now.strftime("%Y-%m")
        admin_token = await _login_admin(client)

        resp = await client.get(
            "/api/v1/admin/analytics/mau",
            params={"months": 1},
            headers=_auth(admin_token),
        )
        baseline = next(r for r in resp.json() if r["month"] == current_month_key)["active_users"]

        await _seed_events(
            [{"event_name": "chat_message_sent", "user_id": None, "event_metadata": {}, "created_at": now}]
        )

        resp = await client.get(
            "/api/v1/admin/analytics/mau",
            params={"months": 1},
            headers=_auth(admin_token),
        )
        after = next(r for r in resp.json() if r["month"] == current_month_key)["active_users"]
        assert after == baseline

    async def test_rejects_non_admin(self, client: AsyncClient):
        resp = await client.get("/api/v1/admin/analytics/mau", params={"months": 6})
        assert resp.status_code == 401


class TestPageViews:
    async def test_counts_page_views_per_day_including_anonymous(self, client: AsyncClient):
        day1 = datetime(2020, 3, 1, 10, tzinfo=timezone.utc)
        day2 = datetime(2020, 3, 2, 10, tzinfo=timezone.utc)
        await _seed_events(
            [
                {"event_name": "page_view", "user_id": "u1", "event_metadata": {}, "created_at": day1},
                {"event_name": "page_view", "user_id": None, "event_metadata": {}, "created_at": day1},
                {"event_name": "page_view", "user_id": "u2", "event_metadata": {}, "created_at": day2},
                # Non-page-view event in range — must be excluded.
                {"event_name": "chat_message_sent", "user_id": "u1", "event_metadata": {}, "created_at": day1},
            ]
        )

        admin_token = await _login_admin(client)
        resp = await client.get(
            "/api/v1/admin/analytics/page-views",
            params={"from": "2020-03-01", "to": "2020-03-31"},
            headers=_auth(admin_token),
        )
        assert resp.status_code == 200, resp.text
        counts = {row["date"]: row["count"] for row in resp.json()}
        assert counts == {"2020-03-01": 2, "2020-03-02": 1}

    async def test_rejects_non_admin(self, client: AsyncClient):
        resp = await client.get(
            "/api/v1/admin/analytics/page-views",
            params={"from": "2020-01-01", "to": "2020-01-31"},
        )
        assert resp.status_code == 401
