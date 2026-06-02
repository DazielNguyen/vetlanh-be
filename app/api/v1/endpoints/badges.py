"""Badge milestone endpoint — US-027."""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_user, get_db
from app.models.user import User
from app.schemas.badge import BadgesResponse
from app.services.badge import get_badges

router = APIRouter(prefix="/badges", tags=["badges"])


@router.get("", response_model=BadgesResponse)
async def list_badges(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """US-027: Return streak count and badge status; marks newly reached milestones as seen."""
    return await get_badges(db, current_user.id)
