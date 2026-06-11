from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_db
from app.schemas.sound import SoundCategory, SoundResponse
from app.services.sound import get_sound, list_sounds

router = APIRouter(prefix="/sounds", tags=["sounds"])


# intentionally public — no auth required per product spec:
# sounds are a discovery/preview feature accessible before login.
@router.get("", response_model=list[SoundResponse])
async def get_sounds(
    category: SoundCategory | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
):
    return await list_sounds(db, category=category)


@router.get("/{sound_id}", response_model=SoundResponse)
async def get_sound_by_id(
    sound_id: str,
    db: AsyncSession = Depends(get_db),
):
    sound = await get_sound(db, sound_id)
    if sound is None:
        raise HTTPException(status_code=404, detail="Sound not found")
    return sound
