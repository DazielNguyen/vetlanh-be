from datetime import date
from typing import Literal

from fastapi import APIRouter, Depends, Query, status
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_user, get_db
from app.models.user import User
from app.schemas.mood import HeatmapResponse, InsightsResponse, MoodEntryCreate, MoodEntryResponse, MoodTrendResponse
from app.services.insights import get_insights
from app.services.mood import create_or_update_entry, get_heatmap, get_trend, list_entries

router = APIRouter(prefix="/mood", tags=["mood"])


@router.post("/entries", response_model=MoodEntryResponse)
async def checkin(
    payload: MoodEntryCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create or update a mood check-in for a given date (today or past dates accepted).

    - First entry for that date → 201 Created
    - Within 1 hour of creation → 200 OK (update allowed)
    - After 1 hour → 409 Conflict
    """
    entry, created = await create_or_update_entry(db, current_user.id, payload)
    # db.commit() is handled by get_db dependency — do not call it here
    status_code = status.HTTP_201_CREATED if created else status.HTTP_200_OK
    return JSONResponse(
        status_code=status_code,
        content=jsonable_encoder(MoodEntryResponse.model_validate(entry)),
    )


@router.get("/entries", response_model=list[MoodEntryResponse])
async def get_entries(
    start: date | None = None,
    end: date | None = None,
    limit: int = Query(default=90, ge=1, le=365),
    offset: int = Query(default=0, ge=0),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List mood entries, optionally filtered by date range (default: last 90 days)."""
    return await list_entries(db, current_user.id, start, end, limit, offset)


@router.get("/insights", response_model=InsightsResponse)
async def get_mood_insights(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Return personalised mood insights from historical check-in data.

    Requires at least 7 check-ins. Returns has_enough_data=false with empty insights list otherwise.
    """
    return await get_insights(db, current_user.id)


@router.get("/heatmap", response_model=HeatmapResponse)
async def get_mood_heatmap(
    year: int = Query(..., ge=2000, le=2100),
    month: int = Query(..., ge=1, le=12),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Return sparse mood heatmap for a given year/month. Only days with entries are included."""
    return await get_heatmap(db, current_user.id, year, month)


@router.get("/trend", response_model=MoodTrendResponse)
async def get_mood_trend(
    period: Literal["week", "month"] = Query(default="week"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Return mood trend data for the last 7 days (week) or 30 days (month).

    Includes a slot for every day in the window; days without a check-in have mood=null.
    """
    return await get_trend(db, current_user.id, period)
