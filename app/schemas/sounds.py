from pydantic import BaseModel


class CloudinaryUploadParams(BaseModel):
    upload_url: str
    api_key: str
    timestamp: int
    signature: str
    folder: str


class SoundResponse(BaseModel):
    id: str
    title: str
    description: str | None
    category: str
    audio_url: str
    duration_seconds: int | None
    sort_order: int
    is_published: bool

    model_config = {"from_attributes": True}


class SoundCreate(BaseModel):
    id: str
    title: str
    description: str | None = None
    category: str
    cloudinary_public_id: str
    audio_url: str
    duration_seconds: int | None = None
    sort_order: int = 0
    is_published: bool = True


class SoundUpdate(BaseModel):
    title: str | None = None
    description: str | None = None
    category: str | None = None
    cloudinary_public_id: str | None = None
    audio_url: str | None = None
    duration_seconds: int | None = None
    sort_order: int | None = None
    is_published: bool | None = None
