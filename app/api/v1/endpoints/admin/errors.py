import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_db, require_admin
from app.models.system_error import SystemError
from app.models.user import User
from app.schemas.error import AdminErrorRow

router = APIRouter()


def _to_row(e: SystemError) -> AdminErrorRow:
    return AdminErrorRow(
        id=e.id,
        timestamp=e.timestamp,
        type=e.error_type,
        route=e.route,
        severity=e.severity,
        status=e.status,
        description=e.description,
    )


@router.get("/errors", response_model=list[AdminErrorRow])
async def list_errors(
    status: str | None = Query(default=None, pattern="^(open|resolved)$"),
    _: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    query = select(SystemError).order_by(SystemError.timestamp.desc())
    if status:
        query = query.where(SystemError.status == status)
    rows = (await db.execute(query)).scalars().all()
    return [_to_row(e) for e in rows]


@router.patch("/errors/{error_id}/resolve", response_model=AdminErrorRow)
async def resolve_error(
    error_id: uuid.UUID,
    _: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    error = await db.get(SystemError, error_id)
    if error is None:
        raise HTTPException(status_code=404, detail="Error not found")

    if error.status == "resolved":
        return _to_row(error)  # idempotent — preserve original resolved_at

    error.status = "resolved"
    error.resolved_at = datetime.now(tz=timezone.utc)
    await db.flush()
    return _to_row(error)
