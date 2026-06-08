from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_db
from app.core.rate_limit import limiter
from app.models.system_error import SystemError
from app.schemas.error import ErrorReportRequest, ErrorReportResponse

router = APIRouter(prefix="/errors", tags=["errors"])


@router.post("/report", response_model=ErrorReportResponse, status_code=201)
@limiter.limit("10/minute")
async def report_error(
    request: Request,
    body: ErrorReportRequest,
    db: AsyncSession = Depends(get_db),
):
    error = SystemError(
        error_type=body.error_type,
        route=body.route,
        severity=body.severity,
        description=body.description,
        status="open",
    )
    db.add(error)
    await db.flush()
    return ErrorReportResponse(id=error.id)
