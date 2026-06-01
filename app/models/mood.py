from datetime import date

from sqlalchemy import Date, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin


class MoodEntry(Base, TimestampMixin):
    __tablename__ = "mood_entries"
    __table_args__ = (UniqueConstraint("user_id", "date", name="uq_mood_user_date"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # Calendar day sent by the client (local date)
    date: Mapped[date] = mapped_column(Date, nullable=False)
    # 1 (😔) to 5 (😄)
    mood: Mapped[int] = mapped_column(Integer, nullable=False)
    # "low" | "medium" | "high"
    energy: Mapped[str | None] = mapped_column(String(10), nullable=True)
    # e.g. ["work", "family", "health", "social"]
    factors: Mapped[list[str]] = mapped_column(
        ARRAY(String(50)), server_default="{}", nullable=False
    )
    note: Mapped[str | None] = mapped_column(String(500), nullable=True)

    user = relationship("User", back_populates="mood_entries")
