from pathlib import PurePosixPath

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.sound import Sound
from app.schemas.sound import SoundCategory, SoundResponse


def _to_response(sound: Sound) -> SoundResponse:
    safe_filename = PurePosixPath(sound.filename).name
    base_url = settings.MEDIA_BASE_URL.rstrip("/")
    return SoundResponse(
        id=sound.id,
        title=sound.title,
        description=sound.description,
        category=sound.category,
        duration_seconds=sound.duration_seconds,
        sort_order=sound.sort_order,
        audio_url=f"{base_url}/media/sounds/{safe_filename}",
    )


async def list_sounds(db: AsyncSession, category: SoundCategory | None = None) -> list[SoundResponse]:
    query = (
        select(Sound)
        .where(Sound.is_published.is_(True))
        .order_by(Sound.sort_order)
    )
    if category:
        query = query.where(Sound.category == category.value)
    result = await db.execute(query)
    return [_to_response(s) for s in result.scalars().all()]


async def get_sound(db: AsyncSession, sound_id: str) -> SoundResponse | None:
    result = await db.execute(
        select(Sound).where(Sound.id == sound_id, Sound.is_published.is_(True))
    )
    sound = result.scalar_one_or_none()
    return _to_response(sound) if sound else None
