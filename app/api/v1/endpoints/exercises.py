from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_user, get_db
from app.models.user import User
from app.schemas.exercise import (
    CATEGORY_LABELS,
    MOOD_FILTER_LABELS,
    ExerciseCategory,
    ExerciseLogCreate,
    ExerciseLogResponse,
    ExerciseResponse,
    MoodFilter,
)
from app.services.exercise import (
    get_exercise,
    get_exercise_history,
    get_recommended,
    list_exercises,
    log_exercise,
)

router = APIRouter(prefix="/exercises", tags=["exercises"])

_NOT_FOUND = "Exercise not found"


@router.get("", response_model=list[ExerciseResponse])
async def list_exercises_endpoint(
    mood: MoodFilter | None = Query(default=None),
    category: ExerciseCategory | None = Query(default=None),
    _: User = Depends(get_current_user),
):
    """US-020: filter by current mood and/or category."""
    return list_exercises(mood=mood, category=category)


@router.get("/recommended", response_model=list[ExerciseResponse])
async def get_recommended_exercises(
    mood: MoodFilter = Query(...),
    limit: int = Query(default=3, ge=1, le=10),
    _: User = Depends(get_current_user),
):
    """US-020: top N exercises for the given mood (used by Dashboard)."""
    return get_recommended(mood=mood, limit=limit)


# /logs routes must be registered BEFORE /{slug} to avoid FastAPI matching
# "logs" as a slug value and returning 404 for these endpoints.
@router.post("/logs", response_model=ExerciseLogResponse, status_code=201)
async def log_completed_exercise(
    payload: ExerciseLogCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Record a completed exercise session for history tracking."""
    try:
        return await log_exercise(db, current_user.id, payload)
    except ValueError:
        raise HTTPException(status_code=404, detail=_NOT_FOUND)


@router.get("/logs/history", response_model=list[ExerciseLogResponse])
async def get_history(
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await get_exercise_history(db, current_user.id, limit=limit, offset=offset)


@router.get("/categories", response_model=list[dict])
async def list_categories():
    """Return all exercise categories with display labels (public, no auth)."""
    return [{"key": c.value, "label": CATEGORY_LABELS[c]} for c in ExerciseCategory]


@router.get("/mood-filters", response_model=list[dict])
async def list_mood_filters():
    """Return all mood filter options with display labels (public, no auth)."""
    return [{"key": m.value, "label": MOOD_FILTER_LABELS[m]} for m in MoodFilter]


# /{slug} must be registered LAST — static path prefixes above take priority.
@router.get("/{slug}", response_model=ExerciseResponse)
async def get_exercise_detail(
    slug: str,
    _: User = Depends(get_current_user),
):
    """US-016/017/018: full exercise detail including phases/steps/audio."""
    exercise = get_exercise(slug)
    if exercise is None:
        raise HTTPException(status_code=404, detail=_NOT_FOUND)
    return exercise
