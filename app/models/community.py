import uuid
from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class CommunityMatch(Base, TimestampMixin):
    __tablename__ = "community_matches"
    __table_args__ = (
        CheckConstraint("user1_id <> user2_id", name="ck_community_match_distinct_users"),
        Index("ix_community_matches_status_created", "status", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user1_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    user2_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    user1_handle: Mapped[str] = mapped_column(String(64), nullable=False)
    user2_handle: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default="active"
    )
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ended_reason: Mapped[str | None] = mapped_column(String(20))


class CommunityParticipation(Base, TimestampMixin):
    __tablename__ = "community_participations"
    __table_args__ = (
        Index("ix_community_participations_status_created", "status", "created_at"),
    )

    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default="opted_out"
    )
    active_match_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("community_matches.id", ondelete="SET NULL"),
        index=True,
    )
    banned_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class CommunityMessage(Base, TimestampMixin):
    __tablename__ = "community_messages"
    __table_args__ = (
        Index("ix_community_messages_match_created", "match_id", "created_at", "id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    match_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("community_matches.id", ondelete="CASCADE"),
        nullable=False,
    )
    sender_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    content: Mapped[str] = mapped_column(Text, nullable=False)


class CommunityBlock(Base, TimestampMixin):
    __tablename__ = "community_blocks"
    __table_args__ = (
        UniqueConstraint("blocker_id", "blocked_id", name="uq_community_block_pair"),
        CheckConstraint("blocker_id <> blocked_id", name="ck_community_block_distinct_users"),
        Index("ix_community_blocks_blocked_id", "blocked_id"),
        Index("ix_community_blocks_expires_at", "expires_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    blocker_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    blocked_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class CommunityReport(Base, TimestampMixin):
    __tablename__ = "community_reports"
    __table_args__ = (
        UniqueConstraint(
            "match_id", "reporter_id", name="uq_community_report_match_reporter"
        ),
        Index("ix_community_reports_status_reported", "status", "reported_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    match_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("community_matches.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    reporter_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    reported_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    reporter_handle: Mapped[str] = mapped_column(String(64), nullable=False)
    reported_handle: Mapped[str] = mapped_column(String(64), nullable=False)
    reason: Mapped[str | None] = mapped_column(String(1000))
    reported_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    sla_deadline: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default="open", index=True
    )
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    resolution: Mapped[str | None] = mapped_column(String(20))
    resolved_by_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )


class CommunityModerationAction(Base):
    __tablename__ = "community_moderation_actions"

    id: Mapped[int] = mapped_column(primary_key=True)
    report_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("community_reports.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    admin_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    action: Mapped[str] = mapped_column(String(20), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
