import logging
from datetime import date
from typing import Literal

from fastapi import APIRouter, Depends, Query, Response, status
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_user, get_db
from app.models.user import User
from app.schemas.mood import HeatmapResponse, InsightsResponse, MoodEntryCreate, MoodEntryResponse, MoodFactor, MoodTrendResponse
from app.services.mood_analysis import enqueue_analysis, get_agentic_insights, schedule_analysis
from app.services.mood import create_or_update_entry, get_heatmap, get_mood_factors, get_trend, list_entries

router = APIRouter(prefix="/mood", tags=["mood"])
logger = logging.getLogger(__name__)


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
    # Commit the check-in before scheduling work so the worker can use an independent
    # session and the model can never extend (or roll back) the save transaction.
    await db.commit()
    try:
        analysis = await enqueue_analysis(db, current_user.id, entry)
        await db.commit()
        schedule_analysis(analysis.id)
    except Exception as exc:
        # Enqueue failure must not turn a successfully saved check-in into an error.
        await db.rollback()
        logger.warning("Could not enqueue mood analysis: %s", type(exc).__name__)
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
    response: Response,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Return personalised mood insights from historical check-in data.

    Reflection generation can start with the first check-in. Weekly deterministic
    insights still require enough history and remain available for older clients.
    """
    response.headers["Cache-Control"] = "private, no-store"
    return await get_agentic_insights(db, current_user.id)


@router.get("/heatmap", response_model=HeatmapResponse)
async def get_mood_heatmap(
    year: int = Query(..., ge=2000, le=2100),
    month: int = Query(..., ge=1, le=12),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Return sparse mood heatmap for a given year/month. Only days with entries are included."""
    return await get_heatmap(db, current_user.id, year, month)


@router.get("/factors", response_model=list[MoodFactor])
async def get_factors():
    """Return the list of mood check-in factors (public, no auth required)."""
    return get_mood_factors()


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
