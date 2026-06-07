from datetime import date, datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_user, get_db
from app.models.user import User
from app.schemas.wellness import WellnessChecklistItem, WellnessChecklistResponse, WellnessItemUpdate
from app.services.wellness import get_wellness_checklist, update_wellness_item

router = APIRouter(prefix="/wellness", tags=["wellness"])

_VN_TZ = timezone(timedelta(hours=7))


def _today_vn() -> date:
    return datetime.now(tz=_VN_TZ).date()


@router.get("/checklist", response_model=WellnessChecklistResponse)
async def get_checklist(
    date: date = Query(default_factory=_today_vn),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Return the daily wellness checklist with completion state for the given date."""
    return await get_wellness_checklist(db, current_user.id, date)


@router.put("/checklist/{item_id}", response_model=WellnessChecklistItem)
async def update_checklist_item(
    item_id: str,
    payload: WellnessItemUpdate,
    date: date = Query(default_factory=_today_vn),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Mark a wellness checklist item as completed or not for the given date (defaults to today)."""
    return await update_wellness_item(db, current_user.id, item_id, payload.completed, date)
