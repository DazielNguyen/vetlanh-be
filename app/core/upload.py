"""File upload utilities — upload to Cloudinary and return the secure URL."""

import asyncio

import cloudinary
import cloudinary.uploader
from fastapi import HTTPException, UploadFile

from app.core.config import settings

cloudinary.config(
    cloud_name=settings.CLOUDINARY_CLOUD_NAME,
    api_key=settings.CLOUDINARY_API_KEY,
    api_secret=settings.CLOUDINARY_API_SECRET,
    secure=True,
)

_MAX_IMAGE_SIZE_BYTES = 10 * 1024 * 1024  # 10 MB
_MAX_AUDIO_SIZE_BYTES = 50 * 1024 * 1024  # 50 MB


def _upload_to_cloudinary(data: bytes, folder: str, resource_type: str) -> dict:
    return cloudinary.uploader.upload(data, folder=folder, resource_type=resource_type)


async def _save_upload(
    file: UploadFile,
    folder: str,
    *,
    mime_prefix: str,
    max_bytes: int,
    resource_type: str,
    label: str,
) -> dict:
    if not (file.content_type or "").startswith(mime_prefix):
        raise HTTPException(status_code=422, detail=f"Only {label} files are accepted")
    contents = await file.read()
    if len(contents) > max_bytes:
        raise HTTPException(status_code=422, detail=f"File exceeds {max_bytes // (1024 * 1024)} MB limit")
    return await asyncio.to_thread(_upload_to_cloudinary, contents, folder, resource_type)


async def save_upload(file: UploadFile, folder: str) -> str:
    """Upload an image file to Cloudinary and return the secure URL."""
    result = await _save_upload(
        file, folder, mime_prefix="image/", max_bytes=_MAX_IMAGE_SIZE_BYTES, resource_type="image", label="image"
    )
    return result["secure_url"]


async def save_audio_upload(file: UploadFile, folder: str) -> tuple[str, str]:
    """Upload an audio file to Cloudinary and return (secure_url, public_id)."""
    result = await _save_upload(
        file, folder, mime_prefix="audio/", max_bytes=_MAX_AUDIO_SIZE_BYTES, resource_type="video", label="audio"
    )
    return result["secure_url"], result["public_id"]
