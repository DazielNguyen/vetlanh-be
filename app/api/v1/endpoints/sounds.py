from fastapi import APIRouter, Depends, HTTPException, UploadFile
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_db, require_admin
from app.core.upload import save_audio_upload
from app.models.sound import Sound
from app.schemas.sounds import SoundCreate, SoundResponse, SoundUpdate

router = APIRouter(prefix="/sounds", tags=["sounds"])


@router.get("", response_model=list[SoundResponse])
async def get_all_sounds(
    category: str | None = None,
    db: AsyncSession = Depends(get_db),
):
    """Return all published sounds, optionally filtered by category."""
    query = select(Sound).where(Sound.is_published.is_(True)).order_by(Sound.sort_order)
    if category:
        query = query.where(Sound.category == category)
    result = await db.execute(query)
    return result.scalars().all()


@router.get("/{sound_id}", response_model=SoundResponse)
async def get_sound(sound_id: str, db: AsyncSession = Depends(get_db)):
    sound = await db.get(Sound, sound_id)
    if sound is None or not sound.is_published:
        raise HTTPException(status_code=404, detail="Sound not found")
    return sound


@router.post("", response_model=SoundResponse, status_code=201)
async def create_sound(
    body: SoundCreate,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_admin),
):
    existing = await db.get(Sound, body.id)
    if existing is not None:
        raise HTTPException(status_code=409, detail="Sound with this id already exists")
    sound = Sound(**body.model_dump())
    db.add(sound)
    await db.flush()
    await db.refresh(sound)
    return sound


@router.post("/{sound_id}/upload", response_model=SoundResponse)
async def upload_sound_file(
    sound_id: str,
    file: UploadFile,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_admin),
):
    sound = await db.get(Sound, sound_id)
    if sound is None:
        raise HTTPException(status_code=404, detail="Sound not found")
    audio_url, public_id = await save_audio_upload(file, "vetlanh/sounds")
    sound.audio_url = audio_url
    sound.cloudinary_public_id = public_id
    await db.flush()
    await db.refresh(sound)
    return sound


@router.patch("/{sound_id}", response_model=SoundResponse)
async def update_sound(
    sound_id: str,
    body: SoundUpdate,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_admin),
):
    sound = await db.get(Sound, sound_id)
    if sound is None:
        raise HTTPException(status_code=404, detail="Sound not found")
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(sound, field, value)
    await db.flush()
    await db.refresh(sound)
    return sound


@router.delete("/{sound_id}", status_code=204)
async def delete_sound(
    sound_id: str,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_admin),
):
    sound = await db.get(Sound, sound_id)
    if sound is None:
        raise HTTPException(status_code=404, detail="Sound not found")
    await db.delete(sound)
