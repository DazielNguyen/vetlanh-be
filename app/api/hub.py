"""SignalR-compatible WebSocket hub — /hubs/app.

Implements the minimal SignalR JSON protocol so the JS client can connect:
  1. POST /hubs/app/negotiate  → validates JWT, issues a short-lived one-time ticket
  2. WS  /hubs/app?id=<ticket> → validates & consumes ticket, handles protocol

Auth uses a one-time opaque ticket (not the raw JWT) for the WebSocket URL.
This avoids JWT exposure in reverse-proxy access logs and browser history, and
binds the negotiate identity to the WebSocket identity.
"""

import asyncio
import json
import logging
import time
import uuid

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Query,
    WebSocket,
    WebSocketDisconnect,
)

from app.core.deps import get_current_user
from app.core.database import AsyncSessionLocal
from app.core.security import decode_access_token
from app.models.user import User
from app.services.auth import get_user_by_email, get_user_by_username

logger = logging.getLogger(__name__)

_RECORD_SEP = "\x1e"                                          # SignalR JSON protocol delimiter (U+001E)
_TICKET_TTL = 30.0                                            # seconds — ticket expires if not consumed
_PONG_FRAME = json.dumps({"type": 6}) + _RECORD_SEP          # pre-serialised SignalR pong

router = APIRouter(prefix="/hubs", tags=["realtime"])

# Pending tickets issued by negotiate, not yet consumed by a WebSocket connect.
# ticket → (user_id, expires_at). Consumed (deleted) on first WebSocket connect.
_pending: dict[str, tuple[int, float]] = {}

# Active WebSocket connections: connectionId → (WebSocket, user_id).
_connections: dict[str, tuple[WebSocket, int]] = {}
_conn_lock = asyncio.Lock()


async def _resolve_user_id_from_token(token: str) -> int:
    """Decode JWT from query param and return user.id, or raise HTTPException 401.

    Used only by hub_websocket where FastAPI DI cannot inject headers-based auth.
    """
    from jose import JWTError
    try:
        subject = decode_access_token(token)
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    async with AsyncSessionLocal() as db:
        user = await (get_user_by_email(db, subject) if "@" in subject else get_user_by_username(db, subject))
    if user is None:
        raise HTTPException(status_code=401, detail="User not found")
    return user.id


def _purge_expired_tickets() -> None:
    now = time.monotonic()
    expired = [t for t, (_, exp) in _pending.items() if exp < now]
    for t in expired:
        _pending.pop(t, None)


@router.post("/app/negotiate")
async def negotiate(current_user: User = Depends(get_current_user)):
    """SignalR negotiation — JS client calls this before opening the WebSocket.

    Issues a short-lived one-time ticket. The client presents the ticket (not the JWT)
    in the WebSocket URL query param, so the JWT is never written to access logs.
    """
    _purge_expired_tickets()
    ticket = str(uuid.uuid4())
    _pending[ticket] = (current_user.id, time.monotonic() + _TICKET_TTL)

    return {
        "negotiateVersion": 1,
        "connectionId": ticket,
        "connectionToken": ticket,
        "availableTransports": [
            {"transport": "WebSockets", "transferFormats": ["Text"]},
        ],
    }


@router.websocket("/app")
async def hub_websocket(
    websocket: WebSocket,
    id: str | None = Query(default=None, include_in_schema=False),
    access_token: str | None = Query(default=None, include_in_schema=False),
):
    """SignalR WebSocket endpoint.

    Client flow:
      1. Send handshake: {"protocol":"json","version":1}\\x1e
      2. Server acks:    {}\\x1e
      3. Exchange typed messages (\\x1e-delimited JSON frames)
      4. Respond to pings (type=6) with pong (type=6)
    """
    ticket = id or access_token
    if not ticket:
        await websocket.close(code=4001, reason="Missing ticket")
        return

    entry = _pending.pop(ticket, None)
    if entry is None or time.monotonic() > entry[1]:
        await websocket.close(code=4001, reason="Invalid or expired ticket")
        return

    user_id = entry[0]
    connection_id = ticket

    await websocket.accept()
    async with _conn_lock:
        _connections[connection_id] = (websocket, user_id)

    try:
        while True:
            try:
                raw = await websocket.receive_text()
            except (WebSocketDisconnect, RuntimeError):
                break

            for frame in raw.split(_RECORD_SEP):
                frame = frame.strip()
                if not frame:
                    continue
                try:
                    msg = json.loads(frame)
                except json.JSONDecodeError:
                    continue

                try:
                    if "protocol" in msg:
                        await websocket.send_text("{}" + _RECORD_SEP)
                    elif msg.get("type") == 6:
                        await websocket.send_text(_PONG_FRAME)
                    elif msg.get("type") == 7:
                        return
                except (WebSocketDisconnect, RuntimeError):
                    return

    finally:
        async with _conn_lock:
            _connections.pop(connection_id, None)


async def send_to_user(user_id: int, target: str, arguments: list) -> None:
    """Push a SignalR invocation to all active connections for a user.

    Usage example:
        await send_to_user(user.id, "ReceiveNotification", [{"title": "...", "body": "..."}])
    """
    msg = json.dumps({"type": 1, "target": target, "arguments": arguments}) + _RECORD_SEP
    async with _conn_lock:
        snapshot = [(cid, ws) for cid, (ws, uid) in _connections.items() if uid == user_id]

    stale: list[str] = []
    for conn_id, ws in snapshot:
        try:
            await ws.send_text(msg)
        except Exception as exc:
            logger.warning("send_to_user: failed to send to %s, dropping: %s", conn_id, exc)
            stale.append(conn_id)

    if stale:
        async with _conn_lock:
            for conn_id in stale:
                _connections.pop(conn_id, None)
