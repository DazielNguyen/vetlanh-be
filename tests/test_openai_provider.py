"""Provider-level tests for the OpenAI Responses API configuration."""

import json
import unittest.mock as mock
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import AsyncClient

from app.core.config import settings
from app.services.chat import _create_response_stream, _safety_identifier


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


def _sse_events(raw_text: str) -> list[dict]:
    return [json.loads(line[len("data: "):]) for line in raw_text.splitlines() if line.startswith("data: ")]


async def _fake_stream(events):
    for event in events:
        yield event


class TestOpenAIChatProvider:
    @pytest.fixture(autouse=True)
    async def clean_db(self):  # noqa: F811
        yield

    @pytest.fixture(autouse=True)
    def mock_email(self):  # noqa: F811
        yield

    async def test_chat_uses_responses_stream_with_privacy_controls(self):
        expected_stream = object()
        create = AsyncMock(return_value=expected_stream)
        client = MagicMock()
        client.responses.create = create
        messages = [{"role": "user", "content": "Xin chào"}]

        with patch("app.services.chat._client", client):
            stream = await _create_response_stream(messages, user_id=42)

        assert stream is expected_stream
        kwargs = create.await_args.kwargs
        assert kwargs["model"] == settings.OPENAI_CHAT_MODEL
        assert kwargs["input"] == messages
        assert kwargs["stream"] is True
        assert kwargs["store"] is False
        assert kwargs["reasoning"] == {"effort": "low"}
        assert kwargs["text"] == {"verbosity": "low"}
        assert kwargs["safety_identifier"] == _safety_identifier(42)

    def test_safety_identifier_is_stable_and_does_not_expose_user_id(self):
        identifier = _safety_identifier(42)
        assert identifier == _safety_identifier(42)
        assert len(identifier) == 64
        assert "42" not in identifier


class TestModelRefusalSurfacesAsError:
    """A refused/empty model turn must produce an `error` SSE event, never a silent
    empty assistant message (contract: docs/openai-model-switch-integration.md §1)."""

    async def _start_conversation(self, client: AsyncClient, email: str) -> tuple[dict, int]:
        token = await _register_and_login(client, email)
        headers = _auth(token)
        conv = await client.post("/api/v1/chat/conversations", json={}, headers=headers)
        assert conv.status_code == 201, conv.text
        return headers, conv.json()["id"]

    async def test_refusal_delta_yields_error_event_not_empty_message(self, client: AsyncClient):
        headers, conv_id = await self._start_conversation(client, "refusal-test@test.vetlanh")
        events = [SimpleNamespace(type="response.refusal.delta", delta="cannot help")]

        with patch("app.services.chat._client") as fake_client:
            fake_client.responses.create = AsyncMock(return_value=_fake_stream(events))
            resp = await client.post(
                f"/api/v1/chat/conversations/{conv_id}/messages",
                json={"content": "Xin chào"},
                headers=headers,
            )

        assert resp.status_code == 200, resp.text
        sse = _sse_events(resp.text)
        types = [e["type"] for e in sse]
        assert "chunk" not in types
        assert "error" in types

        messages = await client.get(f"/api/v1/chat/conversations/{conv_id}/messages", headers=headers)
        assert messages.json() == []

    async def test_empty_stream_yields_error_event_not_empty_message(self, client: AsyncClient):
        headers, conv_id = await self._start_conversation(client, "empty-stream-test@test.vetlanh")

        with patch("app.services.chat._client") as fake_client:
            fake_client.responses.create = AsyncMock(return_value=_fake_stream([]))
            resp = await client.post(
                f"/api/v1/chat/conversations/{conv_id}/messages",
                json={"content": "Xin chào"},
                headers=headers,
            )

        assert resp.status_code == 200, resp.text
        sse = _sse_events(resp.text)
        assert [e["type"] for e in sse] == ["error"]

        messages = await client.get(f"/api/v1/chat/conversations/{conv_id}/messages", headers=headers)
        assert messages.json() == []

    async def test_response_failed_event_yields_error_not_empty_message(self, client: AsyncClient):
        headers, conv_id = await self._start_conversation(client, "response-failed-test@test.vetlanh")
        failed_response = SimpleNamespace(error=SimpleNamespace(message="content management policy violation"))
        events = [SimpleNamespace(type="response.failed", response=failed_response)]

        with patch("app.services.chat._client") as fake_client:
            fake_client.responses.create = AsyncMock(return_value=_fake_stream(events))
            resp = await client.post(
                f"/api/v1/chat/conversations/{conv_id}/messages",
                json={"content": "Xin chào"},
                headers=headers,
            )

        assert resp.status_code == 200, resp.text
        sse = _sse_events(resp.text)
        assert [e["type"] for e in sse] == ["error"]

        messages = await client.get(f"/api/v1/chat/conversations/{conv_id}/messages", headers=headers)
        assert messages.json() == []

    async def test_zero_length_deltas_yield_error_not_empty_message(self, client: AsyncClient):
        """Regression: zero-length `response.output_text.delta` events must not defeat
        the empty-response check by making `full_response` non-empty but contentless."""
        headers, conv_id = await self._start_conversation(client, "zero-delta-test@test.vetlanh")
        events = [
            SimpleNamespace(type="response.output_text.delta", delta=""),
            SimpleNamespace(type="response.output_text.delta", delta=""),
        ]

        with patch("app.services.chat._client") as fake_client:
            fake_client.responses.create = AsyncMock(return_value=_fake_stream(events))
            resp = await client.post(
                f"/api/v1/chat/conversations/{conv_id}/messages",
                json={"content": "Xin chào"},
                headers=headers,
            )

        assert resp.status_code == 200, resp.text
        sse = _sse_events(resp.text)
        types = [e["type"] for e in sse]
        assert "chunk" not in types
        assert types == ["error"]

        messages = await client.get(f"/api/v1/chat/conversations/{conv_id}/messages", headers=headers)
        assert messages.json() == []
