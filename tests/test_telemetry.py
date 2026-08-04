"""Integration tests for the telemetry ingestion endpoint (docs/2026-08-04-be-analytics-events-contract.md)."""

from httpx import AsyncClient
from sqlalchemy import select

from app.core.database import AsyncSessionLocal
from app.models.telemetry import Event


async def _events_for(event_name: str) -> list[Event]:
    async with AsyncSessionLocal() as db:
        rows = (
            await db.execute(select(Event).where(Event.event_name == event_name))
        ).scalars().all()
        return list(rows)


class TestTelemetryPing:
    async def test_accepts_valid_event_with_user_id_and_no_auth_header(self, client: AsyncClient):
        resp = await client.post(
            "/api/v1/telemetry/ping",
            json={"event_name": "chat_message_sent", "user_id": "123", "metadata": {}},
        )
        assert resp.status_code == 202
        rows = await _events_for("chat_message_sent")
        assert any(r.user_id == "123" for r in rows)

    async def test_accepts_valid_event_without_user_id(self, client: AsyncClient):
        resp = await client.post(
            "/api/v1/telemetry/ping",
            json={"event_name": "page_view", "user_id": None, "metadata": {"path": "/"}},
        )
        assert resp.status_code == 202
        rows = await _events_for("page_view")
        assert any(r.user_id is None and r.event_metadata == {"path": "/"} for r in rows)

    async def test_rejects_event_name_outside_allow_list(self, client: AsyncClient):
        resp = await client.post(
            "/api/v1/telemetry/ping",
            json={"event_name": "totally_made_up_event", "user_id": None, "metadata": {}},
        )
        assert resp.status_code == 422
        rows = await _events_for("totally_made_up_event")
        assert rows == []

    async def test_rejects_oversized_metadata(self, client: AsyncClient):
        resp = await client.post(
            "/api/v1/telemetry/ping",
            json={
                "event_name": "chat_message_sent",
                "user_id": None,
                "metadata": {"blob": "x" * 5000},
            },
        )
        assert resp.status_code == 422

    async def test_rejects_oversized_user_id(self, client: AsyncClient):
        resp = await client.post(
            "/api/v1/telemetry/ping",
            json={"event_name": "chat_message_sent", "user_id": "x" * 300, "metadata": {}},
        )
        assert resp.status_code == 422

    async def test_rejects_body_over_content_length_cap(self, client: AsyncClient):
        oversized = {"event_name": "chat_message_sent", "user_id": None, "metadata": {"blob": "y" * 20000}}
        resp = await client.post("/api/v1/telemetry/ping", json=oversized)
        assert resp.status_code in (413, 422)

    async def test_throttles_after_limit_exceeded(self, client: AsyncClient):
        last_status = None
        for _ in range(65):
            resp = await client.post(
                "/api/v1/telemetry/ping",
                json={"event_name": "page_view", "user_id": None, "metadata": {}},
            )
            last_status = resp.status_code
        assert last_status == 429
