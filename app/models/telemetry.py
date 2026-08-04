from datetime import datetime

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class Event(Base):
    __tablename__ = "events"

    id: Mapped[int] = mapped_column(primary_key=True)
    # Client-supplied, unauthenticated, spoofable — never a FK, never trusted for
    # anything beyond directional reporting. Length-capped since it's self-reported.
    user_id: Mapped[str | None] = mapped_column(sa.String(255), nullable=True)
    event_name: Mapped[str] = mapped_column(sa.String(50), nullable=False)
    # "event_metadata" because "metadata" is reserved on DeclarativeBase; the DB
    # column itself is still named "metadata" to match the contract exactly.
    event_metadata: Mapped[dict] = mapped_column("metadata", JSONB, nullable=False, server_default="{}")
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
    )

    __table_args__ = (sa.Index("ix_events_event_name_created_at", "event_name", "created_at"),)
