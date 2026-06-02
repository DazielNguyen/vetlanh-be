from sqlalchemy import ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin


class UserExerciseLog(Base, TimestampMixin):
    __tablename__ = "user_exercise_logs"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # Slug of the static exercise, e.g. "box-breathing", "grounding-54321"
    exercise_slug: Mapped[str] = mapped_column(String(100), nullable=False)
    # Duration in seconds actually completed
    duration_seconds: Mapped[int] = mapped_column(Integer, nullable=False)

    user = relationship("User", back_populates="exercise_logs")
