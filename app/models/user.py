from datetime import datetime

from sqlalchemy import Boolean, DateTime, String
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin


class User(Base, TimestampMixin):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    # nullable=True: OAuth users have no password
    hashed_password: Mapped[str | None] = mapped_column(String(255), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    # "email" for standard registration, "google" for OAuth users
    auth_provider: Mapped[str] = mapped_column(String(20), nullable=False, server_default="email")
    google_id: Mapped[str | None] = mapped_column(String(128), nullable=True, unique=True)

    # Email verification — False until user clicks the link in their inbox
    is_verified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    # Single-use token sent in the verification email; cleared after use
    verification_token: Mapped[str | None] = mapped_column(String(64), nullable=True)
    verification_token_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    goals: Mapped[list] = mapped_column(ARRAY(String(50)), server_default="{}", nullable=False)

    display_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    avatar_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    timezone: Mapped[str | None] = mapped_column(String(64), nullable=True, server_default="Asia/Ho_Chi_Minh")

    assessments = relationship("Assessment", back_populates="user", order_by="Assessment.created_at")
    conversations = relationship("Conversation", back_populates="user", order_by="Conversation.created_at")
