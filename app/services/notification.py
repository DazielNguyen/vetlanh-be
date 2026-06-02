"""Notification preference logic for US-031."""

from datetime import date, datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.mood import MoodEntry
from app.models.notification_preference import NotificationPreference
from app.schemas.notification import (
    NotificationPreferenceOut,
    NotificationPreferenceUpdate,
    ShouldNotifyResponse,
)

_VN_TZ = timezone(timedelta(hours=7))


async def _get_or_create(db: AsyncSession, user_id: int) -> NotificationPreference:
    result = await db.execute(
        select(NotificationPreference).where(NotificationPreference.user_id == user_id)
    )
    pref = result.scalar_one_or_none()
    if pref is None:
        pref = NotificationPreference(user_id=user_id)
        db.add(pref)
        await db.flush()
        await db.refresh(pref)
    return pref


async def get_preference(db: AsyncSession, user_id: int) -> NotificationPreferenceOut:
    pref = await _get_or_create(db, user_id)
    return NotificationPreferenceOut.model_validate(pref)


async def update_preference(
    db: AsyncSession, user_id: int, payload: NotificationPreferenceUpdate
) -> NotificationPreferenceOut:
    pref = await _get_or_create(db, user_id)
    for field in payload.model_fields_set:
        setattr(pref, field, getattr(payload, field))
    await db.flush()
    await db.refresh(pref)
    return NotificationPreferenceOut.model_validate(pref)


def _time_str_to_minutes(t: str) -> int:
    """Convert 'HH:MM' to minutes since midnight."""
    hh, mm = int(t[:2]), int(t[3:])
    return hh * 60 + mm


def _in_quiet_hours(current_minutes: int, quiet_start: str, quiet_end: str) -> bool:
    """Return True if current time falls in the quiet window (handles midnight wrap)."""
    start = _time_str_to_minutes(quiet_start)
    end = _time_str_to_minutes(quiet_end)
    if start > end:
        # Wraps midnight: e.g. 22:00 → 07:00
        return current_minutes >= start or current_minutes < end
    return start <= current_minutes < end


async def should_notify(db: AsyncSession, user_id: int) -> ShouldNotifyResponse:
    pref = await _get_or_create(db, user_id)

    if not pref.enabled:
        return ShouldNotifyResponse(should_notify=False, reason="notifications disabled")

    now_vn = datetime.now(tz=_VN_TZ)
    current_minutes = now_vn.hour * 60 + now_vn.minute

    if _in_quiet_hours(current_minutes, pref.quiet_start, pref.quiet_end):
        return ShouldNotifyResponse(should_notify=False, reason="quiet hours")

    today = now_vn.date()
    result = await db.execute(
        select(MoodEntry).where(MoodEntry.user_id == user_id, MoodEntry.date == today)
    )
    if result.scalar_one_or_none() is not None:
        return ShouldNotifyResponse(should_notify=False, reason="already checked in today")

    return ShouldNotifyResponse(should_notify=True, reason="ok")
