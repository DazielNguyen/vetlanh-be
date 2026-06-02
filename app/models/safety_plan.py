from sqlalchemy import ForeignKey, Text
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin


class UserSafetyPlan(Base, TimestampMixin):
    __tablename__ = "user_safety_plans"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, unique=True, index=True
    )

    # Warning signs the user recognizes in themselves
    warning_signs: Mapped[list] = mapped_column(ARRAY(String(255)), server_default="{}", nullable=False)

    # Activities that help the user calm down
    coping_activities: Mapped[list] = mapped_column(ARRAY(String(255)), server_default="{}", nullable=False)

    # Trusted contacts: stored as ["Name|phone", ...]
    trusted_contacts: Mapped[list] = mapped_column(ARRAY(String(512)), server_default="{}", nullable=False)

    # Personal reasons to keep going
    reasons_to_live: Mapped[str | None] = mapped_column(Text, nullable=True)

    user = relationship("User", back_populates="safety_plan")
