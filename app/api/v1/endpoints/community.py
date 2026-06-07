from fastapi import APIRouter

from app.schemas.community import CommunityFeaturedResponse
from app.services.community import get_community_featured

router = APIRouter(prefix="/community", tags=["community"])


@router.get("/featured", response_model=CommunityFeaturedResponse)
async def community_featured():
    """Return a featured community message — no auth required (public data)."""
    return get_community_featured()
