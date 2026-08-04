import json

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_db
from app.core.rate_limit import limiter
from app.models.telemetry import Event
from app.schemas.telemetry import EventCreate

router = APIRouter()

# Route-scoped only — this is the sole unauthenticated mutating endpoint in the
# API, so it gets a stricter body-size guard than the rest of the app (which
# needs larger bodies for e.g. bill-image uploads).
_MAX_CONTENT_LENGTH_BYTES = 8192


async def _read_body_with_cap(request: Request) -> bytes:
    # Content-Length is a client-supplied hint, not a guarantee — a client can
    # omit it or lie (e.g. chunked transfer-encoding), so the real cap is
    # enforced by aborting the stream read itself, not by trusting the header.
    content_length = request.headers.get("content-length")
    if content_length is not None:
        try:
            declared_length = int(content_length)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid Content-Length header")
        if declared_length > _MAX_CONTENT_LENGTH_BYTES:
            raise HTTPException(status_code=413, detail="Request body too large")

    body = b""
    async for chunk in request.stream():
        body += chunk
        if len(body) > _MAX_CONTENT_LENGTH_BYTES:
            raise HTTPException(status_code=413, detail="Request body too large")
    return body


@router.post("/telemetry/ping", status_code=202)
@limiter.limit("60/minute")
async def ping(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    raw_body = await _read_body_with_cap(request)
    try:
        payload = json.loads(raw_body)
    except json.JSONDecodeError:
        raise HTTPException(status_code=422, detail="Invalid JSON body")

    try:
        body = EventCreate.model_validate(payload)
    except ValidationError as exc:
        errors = [{"loc": e["loc"], "msg": e["msg"], "type": e["type"]} for e in exc.errors()]
        raise HTTPException(status_code=422, detail=errors)

    db.add(Event(user_id=body.user_id, event_name=body.event_name, event_metadata=body.metadata))
    await db.commit()

    return Response(status_code=202)
