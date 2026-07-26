"""Provider-level tests for the OpenAI Responses API configuration."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.core.config import settings
from app.services.chat import _create_response_stream, _safety_identifier


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
