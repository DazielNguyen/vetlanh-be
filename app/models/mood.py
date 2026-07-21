from datetime import date, datetime

from sqlalchemy import Date, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
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


class MoodAnalysis(Base, TimestampMixin):
    """Persistent state for one version of an agentic mood reflection job."""

    __tablename__ = "mood_analyses"
    __table_args__ = (
        UniqueConstraint(
            "user_id",
            "entry_id",
            "entry_updated_at",
            "prompt_version",
            name="uq_mood_analysis_entry_version",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    entry_id: Mapped[int] = mapped_column(
        ForeignKey("mood_entries.id", ondelete="CASCADE"), nullable=False, index=True
    )
    entry_updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    prompt_version: Mapped[str] = mapped_column(String(30), nullable=False)
    # Internal state may also be "stale"; it is never exposed by the API.
    status: Mapped[str] = mapped_column(String(20), nullable=False, server_default="processing")
    generated_by: Mapped[str] = mapped_column(String(10), nullable=False, server_default="rules")
    reflection: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    next_action: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    follow_up_prompt: Mapped[str | None] = mapped_column(Text, nullable=True)
    generated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class MoodAnalysisAudit(Base, TimestampMixin):
    """Metadata-only safety audit. Raw mood notes are deliberately never stored here."""

    __tablename__ = "mood_analysis_audits"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    entry_id: Mapped[int] = mapped_column(
        ForeignKey("mood_entries.id", ondelete="CASCADE"), nullable=False, index=True
    )
    event_type: Mapped[str] = mapped_column(String(50), nullable=False)
