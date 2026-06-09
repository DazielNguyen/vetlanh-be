from sqlalchemy import Enum as SAEnum, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin
from app.schemas.exercise import PostSessionFeeling


class UserExerciseLog(Base, TimestampMixin):
    __tablename__ = "user_exercise_logs"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    exercise_slug: Mapped[str] = mapped_column(String(100), nullable=False)
    duration_seconds: Mapped[int] = mapped_column(Integer, nullable=False)
    # native_enum=False: stored as VARCHAR (length=20 matches migration c07571f977b0), no DB type migration needed
    post_session_feeling: Mapped[PostSessionFeeling | None] = mapped_column(
        SAEnum(PostSessionFeeling, native_enum=False, create_constraint=False, length=20, validate_strings=True),
        nullable=True,
    )

    user = relationship("User", back_populates="exercise_logs")
