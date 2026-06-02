from sqlalchemy import ForeignKey, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin


class ThoughtRecord(Base, TimestampMixin):
    """CBT Thought Record — 5-column structured journal entry (US-019).

    Columns: situation / automatic_thought / emotion / evidence / alternative_thought
    """
    __tablename__ = "thought_records"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )

    # Column 1 — What happened? When/where?
    situation: Mapped[str] = mapped_column(Text, nullable=False)
    # Column 2 — What went through your mind?
    automatic_thought: Mapped[str] = mapped_column(Text, nullable=False)
    # Column 3 — What emotion did you feel? (0–100 intensity)
    emotion: Mapped[str] = mapped_column(Text, nullable=False)
    # Column 4 — Evidence for and against the thought
    evidence: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Column 5 — A more balanced thought
    alternative_thought: Mapped[str | None] = mapped_column(Text, nullable=True)

    user = relationship("User", back_populates="thought_records")
