"""File upload utilities — save UploadFile to local disk and return a relative path."""

import asyncio
import uuid
from pathlib import Path

from fastapi import HTTPException, UploadFile

from app.core.config import settings

_MAX_SIZE_BYTES = 10 * 1024 * 1024  # 10 MB
_ALLOWED_EXTENSIONS = {"jpeg", "jpg", "png", "gif", "webp", "heic", "heif"}


def _write_bytes(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)


async def save_upload(file: UploadFile, subfolder: str) -> str:
    """Save an UploadFile to UPLOADS_DIR/subfolder and return the relative path.

    Raises 422 if content_type is not image/* or file exceeds 10 MB.
    """
    content_type = file.content_type or ""
    if not content_type.startswith("image/"):
        raise HTTPException(status_code=422, detail="Only image files are accepted")

    ext = content_type.split("/")[-1].lower()
    if ext not in _ALLOWED_EXTENSIONS:
        ext = "jpg"

    contents = await file.read()
    if len(contents) > _MAX_SIZE_BYTES:
        raise HTTPException(status_code=422, detail="File exceeds 10 MB limit")

    filename = f"{uuid.uuid4()}.{ext}"
    dest_path = Path(settings.UPLOADS_DIR) / subfolder / filename

    await asyncio.to_thread(_write_bytes, dest_path, contents)

    return str(dest_path)
