from datetime import datetime

from sqlalchemy import Boolean, DateTime, String
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin


class User(Base, TimestampMixin):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    # Email verification — False until user clicks the link in their inbox
    is_verified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    # Single-use token sent in the verification email; cleared after use
    verification_token: Mapped[str | None] = mapped_column(String(64), nullable=True)
    verification_token_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    goals: Mapped[list] = mapped_column(ARRAY(String(50)), server_default="{}", nullable=False)

    assessments = relationship("Assessment", back_populates="user", order_by="Assessment.created_at")
