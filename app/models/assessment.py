from sqlalchemy import ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin


class Assessment(Base, TimestampMixin):
    __tablename__ = "assessments"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)

    # PHQ-9: 9 answers, each 0–3
    q1: Mapped[int] = mapped_column(Integer, nullable=False)
    q2: Mapped[int] = mapped_column(Integer, nullable=False)
    q3: Mapped[int] = mapped_column(Integer, nullable=False)
    q4: Mapped[int] = mapped_column(Integer, nullable=False)
    q5: Mapped[int] = mapped_column(Integer, nullable=False)
    q6: Mapped[int] = mapped_column(Integer, nullable=False)
    q7: Mapped[int] = mapped_column(Integer, nullable=False)
    q8: Mapped[int] = mapped_column(Integer, nullable=False)
    q9: Mapped[int] = mapped_column(Integer, nullable=False)

    score: Mapped[int] = mapped_column(Integer, nullable=False)
    severity: Mapped[str] = mapped_column(String(20), nullable=False)

    user = relationship("User", back_populates="assessments")
