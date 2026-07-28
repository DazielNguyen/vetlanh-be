from fastapi import APIRouter, Depends, Request, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.hub import send_to_user
from app.core.deps import get_current_user, get_db
from app.core.rate_limit import limiter
from app.models.user import User
from app.schemas.community import (
    CommunityFeaturedResponse,
    CommunityMessageCreate,
    CommunityMessageResponse,
    CommunityReportCreate,
    CommunityStatusResponse,
)
from app.services import community as service

router = APIRouter(prefix="/community", tags=["community"])


@router.get("/featured", response_model=CommunityFeaturedResponse)
async def community_featured(db: AsyncSession = Depends(get_db)):
    return await service.get_community_featured(db)


@router.get("/match/status", response_model=CommunityStatusResponse)
async def match_status(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await service.get_match_status(db, current_user.id)


@router.post("/opt-in", response_model=CommunityStatusResponse)
@limiter.limit("100/minute")
async def opt_in(
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    response, partner_id, partner_response = await service.opt_in(db, current_user)
    await db.commit()
    if partner_id is not None and partner_response is not None:
        await send_to_user(
            partner_id,
            "ReceiveCommunityMatch",
            [partner_response.model_dump(by_alias=True, mode="json")["match"]],
        )
    return response


@router.post("/opt-out", status_code=status.HTTP_204_NO_CONTENT)
async def opt_out(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    notify = await service.opt_out(db, current_user.id)
    await db.commit()
    for user_id, match_id in notify:
        await send_to_user(
            user_id, "CommunityMatchEnded", [{"matchId": match_id}]
        )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get(
    "/match/{match_id}/messages", response_model=list[CommunityMessageResponse]
)
async def list_messages(
    match_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await service.list_messages(db, match_id, current_user.id)


@router.post(
    "/match/{match_id}/messages",
    response_model=CommunityMessageResponse,
    status_code=status.HTTP_201_CREATED,
)
@limiter.limit("30/minute")
async def send_message(
    request: Request,
    match_id: str,
    body: CommunityMessageCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    response, partner_response, partner_id = await service.send_message(
        db, match_id, current_user.id, body.content
    )
    await db.commit()
    await send_to_user(
        partner_id,
        "ReceiveCommunityMessage",
        [partner_response.model_dump(by_alias=True, mode="json")],
    )
    return response


async def _notify_match_ended(user_ids: list[int], match_id: str) -> None:
    for user_id in user_ids:
        await send_to_user(
            user_id, "CommunityMatchEnded", [{"matchId": match_id}]
        )


@router.post("/match/{match_id}/exit", status_code=status.HTTP_204_NO_CONTENT)
async def exit_match(
    match_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    partner_id = await service.exit_match(db, match_id, current_user.id)
    await db.commit()
    if partner_id is not None:
        await _notify_match_ended([partner_id], match_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/match/{match_id}/block", status_code=status.HTTP_204_NO_CONTENT)
async def block_match(
    match_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    partner_id = await service.block_match(db, match_id, current_user.id)
    await db.commit()
    await _notify_match_ended([partner_id], match_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/match/{match_id}/report", status_code=status.HTTP_204_NO_CONTENT)
async def report_match(
    match_id: str,
    body: CommunityReportCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    partner_id = await service.report_match(
        db, match_id, current_user.id, body.reason
    )
    await db.commit()
    await _notify_match_ended([partner_id], match_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
