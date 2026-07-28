"""add community matching

Revision ID: e7f8a9b0c1d2
Revises: a1b2c3d4e5f7
Create Date: 2026-07-28
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "e7f8a9b0c1d2"
down_revision: Union[str, None] = "a1b2c3d4e5f7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    uuid_type = postgresql.UUID(as_uuid=True)
    op.create_table(
        "community_matches",
        sa.Column("id", uuid_type, nullable=False),
        sa.Column("user1_id", sa.Integer(), nullable=False),
        sa.Column("user2_id", sa.Integer(), nullable=False),
        sa.Column("user1_handle", sa.String(64), nullable=False),
        sa.Column("user2_handle", sa.String(64), nullable=False),
        sa.Column("status", sa.String(20), server_default="active", nullable=False),
        sa.Column("ended_at", sa.DateTime(timezone=True)),
        sa.Column("ended_reason", sa.String(20)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("user1_id <> user2_id", name="ck_community_match_distinct_users"),
        sa.ForeignKeyConstraint(["user1_id"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["user2_id"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_community_matches_user1_id", "community_matches", ["user1_id"])
    op.create_index("ix_community_matches_user2_id", "community_matches", ["user2_id"])
    op.create_index("ix_community_matches_status_created", "community_matches", ["status", "created_at"])

    op.create_table(
        "community_participations",
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(20), server_default="opted_out", nullable=False),
        sa.Column("active_match_id", uuid_type),
        sa.Column("banned_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["active_match_id"], ["community_matches.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("user_id"),
    )
    op.create_index("ix_community_participations_active_match_id", "community_participations", ["active_match_id"])
    op.create_index("ix_community_participations_status_created", "community_participations", ["status", "created_at"])

    op.create_table(
        "community_messages",
        sa.Column("id", uuid_type, nullable=False),
        sa.Column("match_id", uuid_type, nullable=False),
        sa.Column("sender_id", sa.Integer(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["match_id"], ["community_matches.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["sender_id"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_community_messages_match_created", "community_messages", ["match_id", "created_at", "id"])

    op.create_table(
        "community_blocks",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("blocker_id", sa.Integer(), nullable=False),
        sa.Column("blocked_id", sa.Integer(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("blocker_id <> blocked_id", name="ck_community_block_distinct_users"),
        sa.ForeignKeyConstraint(["blocked_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["blocker_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("blocker_id", "blocked_id", name="uq_community_block_pair"),
    )
    op.create_index("ix_community_blocks_blocker_id", "community_blocks", ["blocker_id"])
    op.create_index("ix_community_blocks_blocked_id", "community_blocks", ["blocked_id"])
    op.create_index("ix_community_blocks_expires_at", "community_blocks", ["expires_at"])

    op.create_table(
        "community_reports",
        sa.Column("id", uuid_type, nullable=False),
        sa.Column("match_id", uuid_type, nullable=False),
        sa.Column("reporter_id", sa.Integer(), nullable=False),
        sa.Column("reported_id", sa.Integer(), nullable=False),
        sa.Column("reporter_handle", sa.String(64), nullable=False),
        sa.Column("reported_handle", sa.String(64), nullable=False),
        sa.Column("reason", sa.String(1000)),
        sa.Column("reported_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("sla_deadline", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(20), server_default="open", nullable=False),
        sa.Column("resolved_at", sa.DateTime(timezone=True)),
        sa.Column("resolution", sa.String(20)),
        sa.Column("resolved_by_id", sa.Integer()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["match_id"], ["community_matches.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["reported_id"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["reporter_id"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["resolved_by_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("match_id", "reporter_id", name="uq_community_report_match_reporter"),
    )
    op.create_index("ix_community_reports_match_id", "community_reports", ["match_id"])
    op.create_index("ix_community_reports_reported_id", "community_reports", ["reported_id"])
    op.create_index("ix_community_reports_status", "community_reports", ["status"])
    op.create_index("ix_community_reports_status_reported", "community_reports", ["status", "reported_at"])

    op.create_table(
        "community_moderation_actions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("report_id", uuid_type, nullable=False),
        sa.Column("admin_user_id", sa.Integer()),
        sa.Column("action", sa.String(20), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["admin_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["report_id"], ["community_reports.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_community_moderation_actions_report_id", "community_moderation_actions", ["report_id"])


def downgrade() -> None:
    op.drop_table("community_moderation_actions")
    op.drop_table("community_reports")
    op.drop_table("community_blocks")
    op.drop_table("community_messages")
    op.drop_table("community_participations")
    op.drop_table("community_matches")
