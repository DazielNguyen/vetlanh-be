from sqlalchemy import Boolean, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class Sound(Base, TimestampMixin):
    __tablename__ = "sounds"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)  # slug, e.g. "stream"
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    category: Mapped[str] = mapped_column(String(64), nullable=False)  # nature | meditation | music | noise
    cloudinary_public_id: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    audio_url: Mapped[str] = mapped_column(Text, nullable=False)
    duration_seconds: Mapped[int | None] = mapped_column(Integer)  # None means looping
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    is_published: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")
