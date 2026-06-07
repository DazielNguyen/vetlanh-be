from fastapi import APIRouter, Depends, Query

from app.core.deps import get_current_user
from app.models.user import User
from app.schemas.resources import ResourceItem
from app.services.resources import get_recommended_resources

router = APIRouter(prefix="/resources", tags=["resources"])


@router.get("/recommended", response_model=list[ResourceItem])
async def recommended_resources(
    limit: int = Query(default=2, ge=1, le=10),
    _: User = Depends(get_current_user),
):
    """Return a curated list of resources tailored for self-healing."""
    return get_recommended_resources(limit=limit)
