from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class Article(Base, TimestampMixin):
    __tablename__ = "articles"

    id: Mapped[str] = mapped_column(String(255), primary_key=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    excerpt: Mapped[str | None] = mapped_column(Text)
    content: Mapped[str | None] = mapped_column(Text)
    category: Mapped[str] = mapped_column(String(64), nullable=False)
    read_minutes: Mapped[int | None] = mapped_column(Integer)
    cover_url: Mapped[str | None] = mapped_column(Text)
    cloudinary_public_id: Mapped[str | None] = mapped_column(String(255), unique=True)
    is_published: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
