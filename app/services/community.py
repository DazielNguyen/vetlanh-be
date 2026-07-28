import secrets
import uuid
from datetime import UTC, datetime, timedelta

from fastapi import HTTPException
from sqlalchemy import and_, exists, func, or_, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.community import (
    CommunityBlock,
    CommunityMatch,
    CommunityMessage,
    CommunityModerationAction,
    CommunityParticipation,
    CommunityReport,
)
from app.models.user import User
from app.schemas.community import (
    CommunityFeaturedResponse,
    CommunityMatchResponse,
    CommunityMessageResponse,
    CommunityReportResponse,
    CommunityStatusResponse,
)

_BLOCK_COOLDOWN_DAYS = 30
_REPORT_SLA_HOURS = 8
_MATCHMAKING_LOCK_ID = 745_219
_FEATURED_MESSAGE = "Bạn không cần phải đi qua những ngày khó khăn một mình."


def _public_id(prefix: str, value: uuid.UUID) -> str:
    return f"{prefix}_{value.hex}"


def _parse_public_id(value: str, prefix: str, detail: str) -> uuid.UUID:
    expected = f"{prefix}_"
    if not value.startswith(expected):
        raise HTTPException(status_code=404, detail=detail)
    try:
        return uuid.UUID(hex=value[len(expected) :])
    except ValueError:
        raise HTTPException(status_code=404, detail=detail) from None


def _new_handle() -> str:
    return f"Người bạn ẩn danh #{secrets.token_hex(2).upper()}"


def _partner_id(match: CommunityMatch, user_id: int) -> int:
    if match.user1_id == user_id:
        return match.user2_id
    if match.user2_id == user_id:
        return match.user1_id
    raise HTTPException(status_code=403, detail="Not a participant of this match")


def _handle_for(match: CommunityMatch, user_id: int) -> str:
    if match.user1_id == user_id:
        return match.user1_handle
    if match.user2_id == user_id:
        return match.user2_handle
    raise HTTPException(status_code=403, detail="Not a participant of this match")


def _status_response(
    participation: CommunityParticipation | None,
    match: CommunityMatch | None,
    user_id: int,
) -> CommunityStatusResponse:
    if participation is None or participation.status == "opted_out":
        return CommunityStatusResponse(status="opted_out")
    if participation.status != "matched" or match is None or match.status != "active":
        return CommunityStatusResponse(status="waiting")
    return CommunityStatusResponse(
        status="matched",
        match=CommunityMatchResponse(
            match_id=_public_id("m", match.id),
            partner_handle=_handle_for(match, _partner_id(match, user_id)),
            matched_at=match.created_at,
        ),
    )


def message_response(
    message: CommunityMessage, caller_id: int
) -> CommunityMessageResponse:
    return CommunityMessageResponse(
        id=_public_id("msg", message.id),
        match_id=_public_id("m", message.match_id),
        content=message.content,
        is_mine=message.sender_id == caller_id,
        created_at=message.created_at,
    )


def report_response(report: CommunityReport) -> CommunityReportResponse:
    return CommunityReportResponse(
        id=_public_id("r", report.id),
        match_id=_public_id("m", report.match_id),
        reporter_handle=report.reporter_handle,
        reported_handle=report.reported_handle,
        reason=report.reason,
        reported_at=report.reported_at,
        sla_deadline=report.sla_deadline,
        status=report.status,
    )


async def _ensure_participation(
    db: AsyncSession, user_id: int
) -> CommunityParticipation:
    await db.execute(
        insert(CommunityParticipation)
        .values(user_id=user_id)
        .on_conflict_do_nothing(index_elements=[CommunityParticipation.user_id])
    )
    return (
        await db.execute(
            select(CommunityParticipation)
            .where(CommunityParticipation.user_id == user_id)
            .with_for_update()
        )
    ).scalar_one()


async def get_match_status(
    db: AsyncSession, user_id: int
) -> CommunityStatusResponse:
    participation = await db.get(CommunityParticipation, user_id)
    match = (
        await db.get(CommunityMatch, participation.active_match_id)
        if participation and participation.active_match_id
        else None
    )
    return _status_response(participation, match, user_id)


async def opt_in(
    db: AsyncSession, user: User
) -> tuple[CommunityStatusResponse, int | None, CommunityStatusResponse | None]:
    if not user.is_active:
        raise HTTPException(status_code=403, detail="Account is deactivated")

    # Serialize only the short matchmaking transaction. This closes the window
    # where simultaneous opt-ins cannot see one another's uncommitted waiting
    # rows and also makes the queue deterministic across app instances.
    await db.execute(select(func.pg_advisory_xact_lock(_MATCHMAKING_LOCK_ID)))
    participation = await _ensure_participation(db, user.id)
    if participation.banned_at is not None:
        raise HTTPException(status_code=403, detail="Community access is suspended")
    if participation.status == "matched" and participation.active_match_id:
        match = await db.get(CommunityMatch, participation.active_match_id)
        return _status_response(participation, match, user.id), None, None

    participation.status = "waiting"
    participation.active_match_id = None
    now = datetime.now(UTC)
    blocked_pair = exists(
        select(CommunityBlock.id).where(
            CommunityBlock.expires_at > now,
            or_(
                and_(
                    CommunityBlock.blocker_id == user.id,
                    CommunityBlock.blocked_id == CommunityParticipation.user_id,
                ),
                and_(
                    CommunityBlock.blocked_id == user.id,
                    CommunityBlock.blocker_id == CommunityParticipation.user_id,
                ),
            ),
        )
    )
    candidate = (
        await db.execute(
            select(CommunityParticipation)
            .join(User, User.id == CommunityParticipation.user_id)
            .where(
                CommunityParticipation.status == "waiting",
                CommunityParticipation.user_id != user.id,
                CommunityParticipation.banned_at.is_(None),
                User.is_active,
                ~blocked_pair,
            )
            .order_by(CommunityParticipation.updated_at, CommunityParticipation.user_id)
            .with_for_update(skip_locked=True)
            .limit(1)
        )
    ).scalar_one_or_none()
    if candidate is None:
        await db.flush()
        return CommunityStatusResponse(status="waiting"), None, None

    match = CommunityMatch(
        user1_id=candidate.user_id,
        user2_id=user.id,
        user1_handle=_new_handle(),
        user2_handle=_new_handle(),
    )
    db.add(match)
    await db.flush()
    candidate.status = participation.status = "matched"
    candidate.active_match_id = participation.active_match_id = match.id
    await db.flush()
    return (
        _status_response(participation, match, user.id),
        candidate.user_id,
        _status_response(candidate, match, candidate.user_id),
    )


async def _load_match_for_participant(
    db: AsyncSession, match_id: str, user_id: int, *, lock: bool = False
) -> CommunityMatch:
    raw_id = _parse_public_id(match_id, "m", "Match not found")
    query = select(CommunityMatch).where(CommunityMatch.id == raw_id)
    if lock:
        query = query.with_for_update()
    match = (await db.execute(query)).scalar_one_or_none()
    if match is None:
        raise HTTPException(status_code=404, detail="Match not found")
    _partner_id(match, user_id)
    return match


async def _end_match(
    db: AsyncSession,
    match: CommunityMatch,
    actor_id: int,
    reason: str,
    *,
    actor_waits: bool,
) -> int:
    partner_id = _partner_id(match, actor_id)
    if match.status == "active":
        match.status = "ended"
        match.ended_at = datetime.now(UTC)
        match.ended_reason = reason
    rows = (
        await db.execute(
            select(CommunityParticipation)
            .where(
                CommunityParticipation.user_id.in_([actor_id, partner_id]),
                CommunityParticipation.active_match_id == match.id,
            )
            .with_for_update()
        )
    ).scalars().all()
    for row in rows:
        row.active_match_id = None
        row.status = "waiting" if row.user_id != actor_id or actor_waits else "opted_out"
    await db.flush()
    return partner_id


async def opt_out(db: AsyncSession, user_id: int) -> list[tuple[int, str]]:
    participation = await _ensure_participation(db, user_id)
    notifications: list[tuple[int, str]] = []
    if participation.active_match_id:
        match = await db.get(
            CommunityMatch, participation.active_match_id, with_for_update=True
        )
        if match:
            partner_id = await _end_match(
                db, match, user_id, "opt_out", actor_waits=False
            )
            notifications.append((partner_id, _public_id("m", match.id)))
    participation.status = "opted_out"
    participation.active_match_id = None
    await db.flush()
    return notifications


async def list_messages(
    db: AsyncSession, match_id: str, user_id: int
) -> list[CommunityMessageResponse]:
    match = await _load_match_for_participant(db, match_id, user_id)
    messages = (
        await db.execute(
            select(CommunityMessage)
            .where(CommunityMessage.match_id == match.id)
            .order_by(CommunityMessage.created_at, CommunityMessage.id)
        )
    ).scalars().all()
    return [message_response(message, user_id) for message in messages]


async def send_message(
    db: AsyncSession, match_id: str, user_id: int, content: str
) -> tuple[CommunityMessageResponse, CommunityMessageResponse, int]:
    match = await _load_match_for_participant(db, match_id, user_id, lock=True)
    if match.status != "active":
        raise HTTPException(status_code=404, detail="Match has ended")
    partner_id = _partner_id(match, user_id)
    message = CommunityMessage(
        match_id=match.id, sender_id=user_id, content=content
    )
    db.add(message)
    await db.flush()
    return (
        message_response(message, user_id),
        message_response(message, partner_id),
        partner_id,
    )


async def exit_match(db: AsyncSession, match_id: str, user_id: int) -> int | None:
    match = await _load_match_for_participant(db, match_id, user_id, lock=True)
    if match.status != "active":
        return None
    return await _end_match(db, match, user_id, "exit", actor_waits=False)


async def block_match(db: AsyncSession, match_id: str, user_id: int) -> int:
    match = await _load_match_for_participant(db, match_id, user_id, lock=True)
    partner_id = _partner_id(match, user_id)
    expires_at = datetime.now(UTC) + timedelta(days=_BLOCK_COOLDOWN_DAYS)
    await db.execute(
        insert(CommunityBlock)
        .values(blocker_id=user_id, blocked_id=partner_id, expires_at=expires_at)
        .on_conflict_do_update(
            constraint="uq_community_block_pair",
            set_={"expires_at": expires_at, "updated_at": func.now()},
        )
    )
    if match.status == "active":
        await _end_match(db, match, user_id, "block", actor_waits=True)
    return partner_id


async def report_match(
    db: AsyncSession, match_id: str, user_id: int, reason: str | None
) -> int:
    match = await _load_match_for_participant(db, match_id, user_id, lock=True)
    reported_id = _partner_id(match, user_id)
    existing = (
        await db.execute(
            select(CommunityReport).where(
                CommunityReport.match_id == match.id,
                CommunityReport.reporter_id == user_id,
            )
        )
    ).scalar_one_or_none()
    if existing is not None:
        return reported_id
    now = datetime.now(UTC)
    report = CommunityReport(
        match_id=match.id,
        reporter_id=user_id,
        reported_id=reported_id,
        reporter_handle=_handle_for(match, user_id),
        reported_handle=_handle_for(match, reported_id),
        reason=reason,
        reported_at=now,
        sla_deadline=now + timedelta(hours=_REPORT_SLA_HOURS),
    )
    db.add(report)
    if match.status == "active":
        await _end_match(db, match, user_id, "report", actor_waits=False)
    await db.flush()
    return reported_id


async def get_community_featured(db: AsyncSession) -> CommunityFeaturedResponse:
    active_count = (
        await db.execute(
            select(func.count())
            .select_from(CommunityParticipation)
            .join(User, User.id == CommunityParticipation.user_id)
            .where(
                CommunityParticipation.status.in_(["waiting", "matched"]),
                CommunityParticipation.banned_at.is_(None),
                User.is_active,
            )
        )
    ).scalar_one()
    return CommunityFeaturedResponse(
        message=_FEATURED_MESSAGE,
        author_display="Cộng đồng Vết Lành",
        active_users_count=active_count,
    )


async def list_reports(
    db: AsyncSession, status: str
) -> list[CommunityReportResponse]:
    reports = (
        await db.execute(
            select(CommunityReport)
            .where(CommunityReport.status == status)
            .order_by(CommunityReport.reported_at.desc())
        )
    ).scalars().all()
    return [report_response(report) for report in reports]


async def moderate_report(
    db: AsyncSession,
    report_id: str,
    action: str,
    admin_id: int,
) -> tuple[CommunityReportResponse, list[int], int | None]:
    raw_id = _parse_public_id(report_id, "r", "Report not found")
    report = (
        await db.execute(
            select(CommunityReport)
            .where(CommunityReport.id == raw_id)
            .with_for_update()
        )
    ).scalar_one_or_none()
    if report is None or report.status == "resolved":
        raise HTTPException(status_code=404, detail="Report not found")

    now = datetime.now(UTC)
    report.status = "resolved"
    report.resolved_at = now
    report.resolution = action
    report.resolved_by_id = admin_id
    db.add(
        CommunityModerationAction(
            report_id=report.id,
            admin_user_id=admin_id,
            action=action,
            created_at=now,
        )
    )
    notify: list[int] = []
    warning_user_id: int | None = None
    if action == "warn":
        warning_user_id = report.reported_id
    elif action == "unmatch":
        match = await db.get(CommunityMatch, report.match_id, with_for_update=True)
        if match and match.status == "active":
            await _end_match(
                db, match, report.reported_id, "admin_unmatch", actor_waits=True
            )
            notify = [match.user1_id, match.user2_id]
    elif action == "ban":
        participation = await _ensure_participation(db, report.reported_id)
        if participation.active_match_id:
            match = await db.get(
                CommunityMatch, participation.active_match_id, with_for_update=True
            )
            if match and match.status == "active":
                partner_id = await _end_match(
                    db, match, report.reported_id, "admin_ban", actor_waits=False
                )
                notify = [report.reported_id, partner_id]
        participation.status = "opted_out"
        participation.active_match_id = None
        participation.banned_at = now
    await db.flush()
    return report_response(report), notify, warning_user_id
