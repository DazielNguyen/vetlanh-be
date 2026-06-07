"""
Integration tests for the SignalR-compatible WebSocket hub — /hubs/app.

Covers:
  POST /hubs/app/negotiate:
    - No auth header → 401/403 (FastAPI HTTPBearer)
    - Invalid token → 401
    - Valid token → 200 with required SignalR negotiate fields
    - Each call returns a unique connectionId
    - availableTransports includes WebSockets

  WebSocket /hubs/app:
    - No access_token query param → server sends close with code 4001
    - Invalid access_token → server sends close with code 4001
    - Valid token → connection accepted (server sends websocket.accept)
    - Handshake: send {"protocol":"json","version":1}\\x1e → receive {}\\x1e
    - Ping (type 6): send {"type":6}\\x1e → receive {"type":6}\\x1e
    - Close (type 7): server closes cleanly (handler returns)
    - Multiple frames concatenated in one message are all handled
    - Unknown message type is silently ignored (no response)
    - Malformed JSON frame is silently ignored (no response)
    - ?id=... query param is accepted without error

The tests use a raw ASGI WebSocket driver so they run on the same asyncio
event loop as the asyncpg connection pool, avoiding "Future attached to a
different loop" errors that occur with starlette.testclient.TestClient.
"""

import asyncio
import json
from contextlib import asynccontextmanager
from typing import AsyncGenerator
from urllib.parse import urlencode

import pytest
from httpx import AsyncClient
from sqlalchemy import text

from app.core.database import AsyncSessionLocal

_RECORD_SEP = "\x1e"
NEGOTIATE_URL = "/hubs/app/negotiate"
WS_PATH = "/hubs/app"

# Prefix used for all hub-test usernames so we can wipe them between tests.
_HUB_USERNAME_PREFIX = "hub_"


@pytest.fixture(autouse=True)
async def clean_hub_users():
    """Delete hub-test users (identified by username prefix) before each test.

    The shared conftest.py clean_db only removes users by email domain, but
    hub tests register username-only accounts. This fixture ensures a clean
    state regardless of which tests ran before.
    """
    async with AsyncSessionLocal() as db:
        await db.execute(
            text("DELETE FROM users WHERE username LIKE :prefix"),
            {"prefix": _HUB_USERNAME_PREFIX + "%"},
        )
        await db.commit()
    yield


# ---------------------------------------------------------------------------
# Raw async ASGI WebSocket driver
# ---------------------------------------------------------------------------

class _ASGIWebSocket:
    """Drives a WebSocket ASGI endpoint from the test's own event loop.

    Usage::
        async with _ASGIWebSocket(app, "/path?foo=bar") as ws:
            ws.send({"type": 6})
            msg = await ws.recv()
    """

    def __init__(self, asgi_app, path: str):
        from urllib.parse import urlparse, parse_qs
        parsed = urlparse(path)
        self._app = asgi_app
        self._path = parsed.path
        self._qs = (parsed.query or "").encode()
        self._incoming: asyncio.Queue = asyncio.Queue()
        self._outgoing: asyncio.Queue = asyncio.Queue()
        self._task: asyncio.Task | None = None
        self.accepted = False
        self.close_code: int | None = None

    async def __aenter__(self):
        scope = {
            "type": "websocket",
            "asgi": {"version": "3.0"},
            "http_version": "1.1",
            "method": "GET",
            "headers": [
                (b"host", b"testserver"),
                (b"connection", b"upgrade"),
                (b"upgrade", b"websocket"),
                (b"sec-websocket-key", b"testserver=="),
                (b"sec-websocket-version", b"13"),
            ],
            "path": self._path,
            "query_string": self._qs,
            "root_path": "",
            "scheme": "ws",
            "server": ("testserver", 80),
            "client": ("testclient", 50000),
            "subprotocols": [],
        }

        async def receive():
            return await self._incoming.get()

        async def send(message):
            await self._outgoing.put(message)

        # Send the initial connect event
        await self._incoming.put({"type": "websocket.connect"})
        # Run the ASGI app as a background task so we can drive it interactively
        self._task = asyncio.create_task(self._app(scope, receive, send))
        # Read the first server message (accept or close)
        first = await asyncio.wait_for(self._outgoing.get(), timeout=5.0)
        if first["type"] == "websocket.accept":
            self.accepted = True
        elif first["type"] == "websocket.close":
            self.close_code = first.get("code", 1000)
            # Cancel the app task since the connection was rejected
            self._task.cancel()
            raise ConnectionRefusedError(
                f"WebSocket closed before accept: code={self.close_code}"
            )
        return self

    async def __aexit__(self, *exc_info):
        # Disconnect so the server loop exits cleanly
        try:
            await self._incoming.put({"type": "websocket.disconnect", "code": 1000})
        except Exception:
            pass
        if self._task:
            try:
                await asyncio.wait_for(self._task, timeout=3.0)
            except Exception:
                self._task.cancel()

    async def send_text(self, text: str) -> None:
        """Send a text frame to the server."""
        await self._incoming.put({"type": "websocket.receive", "text": text})

    async def recv(self, timeout: float = 5.0) -> dict:
        """Receive the next message sent by the server."""
        return await asyncio.wait_for(self._outgoing.get(), timeout=timeout)

    async def recv_text(self, timeout: float = 5.0) -> str:
        msg = await self.recv(timeout=timeout)
        return msg.get("text", "")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _signalr_frame(obj: dict) -> str:
    """Encode a dict as a SignalR JSON frame (record-separator terminated)."""
    return json.dumps(obj) + _RECORD_SEP


async def _register_and_login(client: AsyncClient, username: str) -> str:
    """Register a username-only user and return an access token."""
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


def _auth_header(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _ws_url(token: str | None = None, conn_id: str | None = None) -> str:
    params = {}
    if token:
        params["access_token"] = token
    if conn_id:
        params["id"] = conn_id
    qs = urlencode(params)
    return f"{WS_PATH}?{qs}" if qs else WS_PATH


async def _get_ticket(client: AsyncClient, token: str) -> str:
    """Negotiate a one-time ticket for the WebSocket connection."""
    resp = await client.post(NEGOTIATE_URL, headers=_auth_header(token))
    assert resp.status_code == 200, f"Negotiate failed: {resp.text}"
    return resp.json()["connectionToken"]


# ---------------------------------------------------------------------------
# Fixture: get the ASGI app directly for the WebSocket driver
# ---------------------------------------------------------------------------

@pytest.fixture
def asgi_app():
    from app.main import app as _app
    return _app


# ===========================================================================
# POST /hubs/app/negotiate
# ===========================================================================

class TestNegotiate:

    async def test_no_auth_header_returns_4xx(self, client: AsyncClient):
        """No Authorization header → 401 or 403 (HTTPBearer behaviour)."""
        resp = await client.post(NEGOTIATE_URL)
        assert resp.status_code in (401, 403)

    async def test_invalid_token_returns_401(self, client: AsyncClient):
        resp = await client.post(
            NEGOTIATE_URL,
            headers={"Authorization": "Bearer this.is.not.valid"},
        )
        assert resp.status_code == 401

    async def test_malformed_bearer_returns_4xx(self, client: AsyncClient):
        """'Bearer' with no token value → 401 or 422."""
        resp = await client.post(
            NEGOTIATE_URL,
            headers={"Authorization": "Bearer "},
        )
        assert resp.status_code in (401, 403, 422)

    async def test_valid_token_returns_200(self, client: AsyncClient):
        token = await _register_and_login(client, "hub_neg_200")
        resp = await client.post(NEGOTIATE_URL, headers=_auth_header(token))
        assert resp.status_code == 200

    async def test_negotiate_response_has_required_fields(self, client: AsyncClient):
        token = await _register_and_login(client, "hub_neg_fields")
        resp = await client.post(NEGOTIATE_URL, headers=_auth_header(token))
        data = resp.json()
        assert data["negotiateVersion"] == 1
        assert "connectionId" in data
        assert "connectionToken" in data
        assert "availableTransports" in data

    async def test_negotiate_version_is_1(self, client: AsyncClient):
        token = await _register_and_login(client, "hub_neg_ver")
        resp = await client.post(NEGOTIATE_URL, headers=_auth_header(token))
        assert resp.json()["negotiateVersion"] == 1

    async def test_negotiate_connection_id_is_non_empty_string(self, client: AsyncClient):
        token = await _register_and_login(client, "hub_neg_connid")
        resp = await client.post(NEGOTIATE_URL, headers=_auth_header(token))
        data = resp.json()
        assert isinstance(data["connectionId"], str)
        assert len(data["connectionId"]) > 0

    async def test_connection_token_equals_connection_id(self, client: AsyncClient):
        token = await _register_and_login(client, "hub_neg_conntoken")
        resp = await client.post(NEGOTIATE_URL, headers=_auth_header(token))
        data = resp.json()
        assert data["connectionToken"] == data["connectionId"]

    async def test_negotiate_available_transports_contains_websockets(self, client: AsyncClient):
        token = await _register_and_login(client, "hub_neg_transports")
        resp = await client.post(NEGOTIATE_URL, headers=_auth_header(token))
        transports = resp.json()["availableTransports"]
        assert isinstance(transports, list)
        assert len(transports) > 0
        names = [t["transport"] for t in transports]
        assert "WebSockets" in names

    async def test_websockets_transport_has_text_format(self, client: AsyncClient):
        token = await _register_and_login(client, "hub_neg_txtformat")
        resp = await client.post(NEGOTIATE_URL, headers=_auth_header(token))
        ws_transport = next(
            t for t in resp.json()["availableTransports"]
            if t["transport"] == "WebSockets"
        )
        assert "Text" in ws_transport["transferFormats"]

    async def test_each_call_returns_unique_connection_id(self, client: AsyncClient):
        token = await _register_and_login(client, "hub_neg_unique")
        headers = _auth_header(token)
        resp1 = await client.post(NEGOTIATE_URL, headers=headers)
        resp2 = await client.post(NEGOTIATE_URL, headers=headers)
        assert resp1.json()["connectionId"] != resp2.json()["connectionId"]


# ===========================================================================
# WebSocket /hubs/app — auth rejection
# ===========================================================================

class TestWebSocketAuth:

    async def test_missing_token_closes_with_4001(self, asgi_app):
        """No access_token → server closes with 4001 before accepting."""
        ws = _ASGIWebSocket(asgi_app, WS_PATH)
        with pytest.raises(ConnectionRefusedError):
            await ws.__aenter__()
        assert ws.close_code == 4001

    async def test_empty_token_closes_with_4001(self, asgi_app):
        """access_token= (empty) → server closes with 4001."""
        ws = _ASGIWebSocket(asgi_app, f"{WS_PATH}?access_token=")
        with pytest.raises(ConnectionRefusedError):
            await ws.__aenter__()
        assert ws.close_code == 4001

    async def test_invalid_token_closes_with_4001(self, asgi_app):
        """Malformed JWT → server closes with 4001."""
        ws = _ASGIWebSocket(asgi_app, f"{WS_PATH}?access_token=bad.token.value")
        with pytest.raises(ConnectionRefusedError):
            await ws.__aenter__()
        assert ws.close_code == 4001


# ===========================================================================
# WebSocket /hubs/app — happy-path protocol flows
# ===========================================================================

class TestWebSocketProtocol:

    async def test_valid_token_accepts_connection(self, client: AsyncClient, asgi_app):
        """A valid JWT negotiated to a ticket → server sends websocket.accept."""
        token = await _register_and_login(client, "hub_ws_connect")
        ticket = await _get_ticket(client, token)
        async with _ASGIWebSocket(asgi_app, _ws_url(conn_id=ticket)) as ws:
            assert ws.accepted is True

    async def test_handshake_receives_ack(self, client: AsyncClient, asgi_app):
        """Send handshake frame → receive empty-object ack."""
        token = await _register_and_login(client, "hub_ws_handshake")
        ticket = await _get_ticket(client, token)
        async with _ASGIWebSocket(asgi_app, _ws_url(conn_id=ticket)) as ws:
            await ws.send_text(_signalr_frame({"protocol": "json", "version": 1}))
            raw = await ws.recv_text()
        frames = [f for f in raw.split(_RECORD_SEP) if f.strip()]
        assert len(frames) >= 1
        assert json.loads(frames[0]) == {}

    async def test_ping_receives_pong(self, client: AsyncClient, asgi_app):
        """Send type=6 ping → receive type=6 pong."""
        token = await _register_and_login(client, "hub_ws_ping")
        ticket = await _get_ticket(client, token)
        async with _ASGIWebSocket(asgi_app, _ws_url(conn_id=ticket)) as ws:
            await ws.send_text(_signalr_frame({"protocol": "json", "version": 1}))
            await ws.recv_text()  # discard handshake ack
            await ws.send_text(_signalr_frame({"type": 6}))
            raw = await ws.recv_text()

        frames = [f for f in raw.split(_RECORD_SEP) if f.strip()]
        assert len(frames) >= 1
        assert json.loads(frames[0]) == {"type": 6}

    async def test_close_type7_closes_cleanly(self, client: AsyncClient, asgi_app):
        """Send type=7 → server returns from handler without error."""
        token = await _register_and_login(client, "hub_ws_close7")
        ticket = await _get_ticket(client, token)
        async with _ASGIWebSocket(asgi_app, _ws_url(conn_id=ticket)) as ws:
            await ws.send_text(_signalr_frame({"protocol": "json", "version": 1}))
            await ws.recv_text()
            await ws.send_text(_signalr_frame({"type": 7}))
            await asyncio.sleep(0.05)
        # If we exit without an unhandled exception the test passes

    async def test_multiple_frames_in_single_message(self, client: AsyncClient, asgi_app):
        """Handshake + ping concatenated in one send are both processed."""
        token = await _register_and_login(client, "hub_ws_multiframe")
        ticket = await _get_ticket(client, token)
        async with _ASGIWebSocket(asgi_app, _ws_url(conn_id=ticket)) as ws:
            combined = (
                _signalr_frame({"protocol": "json", "version": 1})
                + _signalr_frame({"type": 6})
            )
            await ws.send_text(combined)

            raw1 = await ws.recv_text()
            frames1 = [f for f in raw1.split(_RECORD_SEP) if f.strip()]
            assert json.loads(frames1[0]) == {}

            raw2 = await ws.recv_text()
            frames2 = [f for f in raw2.split(_RECORD_SEP) if f.strip()]
            assert json.loads(frames2[0]) == {"type": 6}

    async def test_unknown_message_type_produces_no_reply(self, client: AsyncClient, asgi_app):
        """Unknown message type is silently ignored — only the subsequent ping is answered."""
        token = await _register_and_login(client, "hub_ws_unknown")
        ticket = await _get_ticket(client, token)
        async with _ASGIWebSocket(asgi_app, _ws_url(conn_id=ticket)) as ws:
            await ws.send_text(_signalr_frame({"protocol": "json", "version": 1}))
            await ws.recv_text()
            await ws.send_text(_signalr_frame({"type": 99}))
            await ws.send_text(_signalr_frame({"type": 6}))
            raw = await ws.recv_text(timeout=3.0)
        frames = [f for f in raw.split(_RECORD_SEP) if f.strip()]
        assert json.loads(frames[0]) == {"type": 6}

    async def test_malformed_json_is_ignored(self, client: AsyncClient, asgi_app):
        """Non-JSON frame is skipped; subsequent valid frame is still processed."""
        token = await _register_and_login(client, "hub_ws_malformed")
        ticket = await _get_ticket(client, token)
        async with _ASGIWebSocket(asgi_app, _ws_url(conn_id=ticket)) as ws:
            await ws.send_text(_signalr_frame({"protocol": "json", "version": 1}))
            await ws.recv_text()
            await ws.send_text("this is not json" + _RECORD_SEP)
            await ws.send_text(_signalr_frame({"type": 6}))
            raw = await ws.recv_text(timeout=3.0)
        frames = [f for f in raw.split(_RECORD_SEP) if f.strip()]
        assert json.loads(frames[0]) == {"type": 6}

    async def test_empty_frame_between_valid_frames_is_skipped(self, client: AsyncClient, asgi_app):
        """Empty string frames (after splitting on record separator) are skipped."""
        token = await _register_and_login(client, "hub_ws_empty_frame")
        ticket = await _get_ticket(client, token)
        async with _ASGIWebSocket(asgi_app, _ws_url(conn_id=ticket)) as ws:
            payload = _RECORD_SEP + _signalr_frame({"protocol": "json", "version": 1})
            await ws.send_text(payload)
            raw = await ws.recv_text()
        frames = [f for f in raw.split(_RECORD_SEP) if f.strip()]
        assert json.loads(frames[0]) == {}

    async def test_connection_id_query_param_is_accepted(self, client: AsyncClient, asgi_app):
        """Ticket passed as ?id= query param is accepted and connection is established."""
        token = await _register_and_login(client, "hub_ws_connid_param")
        ticket = await _get_ticket(client, token)
        async with _ASGIWebSocket(asgi_app, _ws_url(conn_id=ticket)) as ws:
            await ws.send_text(_signalr_frame({"protocol": "json", "version": 1}))
            raw = await ws.recv_text()
        frames = [f for f in raw.split(_RECORD_SEP) if f.strip()]
        assert json.loads(frames[0]) == {}

    async def test_multiple_pings_all_answered(self, client: AsyncClient, asgi_app):
        """Each ping should receive exactly one pong."""
        token = await _register_and_login(client, "hub_ws_multi_ping")
        ticket = await _get_ticket(client, token)
        async with _ASGIWebSocket(asgi_app, _ws_url(conn_id=ticket)) as ws:
            await ws.send_text(_signalr_frame({"protocol": "json", "version": 1}))
            await ws.recv_text()
            for _ in range(3):
                await ws.send_text(_signalr_frame({"type": 6}))
                raw = await ws.recv_text()
                frames = [f for f in raw.split(_RECORD_SEP) if f.strip()]
                assert json.loads(frames[0]) == {"type": 6}
