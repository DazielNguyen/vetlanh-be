from typing import Literal

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.hub import send_to_user
from app.core.deps import get_db, require_admin
from app.models.user import User
from app.schemas.community import CommunityReportResponse
from app.services.community import list_reports, moderate_report

router = APIRouter()


@router.get("/community/reports", response_model=list[CommunityReportResponse])
async def get_reports(
    status: Literal["open", "resolved"] = Query(default="open"),
    _: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    return await list_reports(db, status)


async def _moderate(
    report_id: str, action: str, admin: User, db: AsyncSession
) -> CommunityReportResponse:
    report, notify, warning_user_id = await moderate_report(
        db, report_id, action, admin.id
    )
    await db.commit()
    if warning_user_id is not None:
        # The event intentionally carries no reporter identity or report details.
        # Clients that do not subscribe simply ignore it.
        await send_to_user(
            warning_user_id,
            "CommunityWarning",
            [{"message": "Tài khoản của bạn đã nhận cảnh báo về quy tắc cộng đồng."}],
        )
    for user_id in notify:
        await send_to_user(
            user_id,
            "CommunityMatchEnded",
            [{"matchId": report.match_id}],
        )
    return report


@router.post(
    "/community/reports/{report_id}/warn",
    response_model=CommunityReportResponse,
)
async def warn(
    report_id: str,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    return await _moderate(report_id, "warn", admin, db)


@router.post(
    "/community/reports/{report_id}/unmatch",
    response_model=CommunityReportResponse,
)
async def unmatch(
    report_id: str,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    return await _moderate(report_id, "unmatch", admin, db)


@router.post(
    "/community/reports/{report_id}/ban",
    response_model=CommunityReportResponse,
)
async def ban(
    report_id: str,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    return await _moderate(report_id, "ban", admin, db)
