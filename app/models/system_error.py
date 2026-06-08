import uuid
from datetime import datetime

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class SystemError(Base):
    __tablename__ = "system_errors"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    timestamp: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")
    )
    error_type: Mapped[str] = mapped_column(sa.String(100), nullable=False)
    route: Mapped[str | None] = mapped_column(sa.String(500), nullable=True)
    severity: Mapped[str] = mapped_column(
        sa.String(10), nullable=False, server_default="HIGH"
    )  # HIGH | MEDIUM | LOW
    description: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    status: Mapped[str] = mapped_column(
        sa.String(20), nullable=False, server_default="open"
    )  # open | resolved
    resolved_at: Mapped[datetime | None] = mapped_column(
        sa.DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
    )
