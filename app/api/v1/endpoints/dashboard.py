"""Dashboard aggregate endpoint — US-026."""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_user, get_db
from app.models.user import User
from app.schemas.dashboard import (
    DailyQuoteResponse,
    DashboardResponse,
    PersonalizedRecommendationResponse,
)
from app.services.dashboard import get_daily_quote, get_dashboard
from app.services.recommendation import get_personalized_recommendation

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("", response_model=DashboardResponse)
async def get_home_dashboard(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """US-026: Home dashboard — greeting, mood status, streak, 7-day sparkline, recommendations."""
    return await get_dashboard(db, current_user)


@router.get("/quote", response_model=DailyQuoteResponse)
async def get_quote(_: User = Depends(get_current_user)):
    """Return today's motivational quote (rotates daily)."""
    return get_daily_quote()


@router.get(
    "/personalized-recommendation",
    response_model=PersonalizedRecommendationResponse | None,
)
async def get_personalized_recommendation_route(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Rule-based single exercise recommendation, or null when there isn't enough
    history yet. A DB read failure propagates as a normal 5xx — never coerced into
    a null response, which would misrepresent an infrastructure failure as
    "insufficient data"."""
    result = await get_personalized_recommendation(db, current_user.id)
    if result is None:
        return None
    return PersonalizedRecommendationResponse(
        title=result.title, rationale=result.rationale, url=result.url
    )
