from enum import Enum

from pydantic import BaseModel


class SoundCategory(str, Enum):
    nature = "nature"
    meditation = "meditation"
    music = "music"
    noise = "noise"


class SoundResponse(BaseModel):
    id: str
    title: str
    description: str | None
    category: SoundCategory
    duration_seconds: int | None
    sort_order: int
    audio_url: str

    model_config = {"from_attributes": True}
