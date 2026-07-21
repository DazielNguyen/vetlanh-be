"""add mood agentic analyses

Revision ID: d6e7f8a9b0c1
Revises: c5d6e7f8a9b0
Create Date: 2026-07-21 00:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "d6e7f8a9b0c1"
down_revision: Union[str, None] = "c5d6e7f8a9b0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "mood_analyses",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("entry_id", sa.Integer(), nullable=False),
        sa.Column("entry_updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("prompt_version", sa.String(length=30), nullable=False),
        sa.Column("status", sa.String(length=20), server_default="processing", nullable=False),
        sa.Column("generated_by", sa.String(length=10), server_default="rules", nullable=False),
        sa.Column("reflection", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("next_action", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("follow_up_prompt", sa.Text(), nullable=True),
        sa.Column("generated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["entry_id"], ["mood_entries.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "user_id", "entry_id", "entry_updated_at", "prompt_version",
            name="uq_mood_analysis_entry_version",
        ),
    )
    op.create_index("ix_mood_analyses_user_id", "mood_analyses", ["user_id"])
    op.create_index("ix_mood_analyses_entry_id", "mood_analyses", ["entry_id"])

    op.create_table(
        "mood_analysis_audits",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("entry_id", sa.Integer(), nullable=False),
        sa.Column("event_type", sa.String(length=50), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["entry_id"], ["mood_entries.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_mood_analysis_audits_user_id", "mood_analysis_audits", ["user_id"])
    op.create_index("ix_mood_analysis_audits_entry_id", "mood_analysis_audits", ["entry_id"])


def downgrade() -> None:
    op.drop_index("ix_mood_analysis_audits_entry_id", table_name="mood_analysis_audits")
    op.drop_index("ix_mood_analysis_audits_user_id", table_name="mood_analysis_audits")
    op.drop_table("mood_analysis_audits")
    op.drop_index("ix_mood_analyses_entry_id", table_name="mood_analyses")
    op.drop_index("ix_mood_analyses_user_id", table_name="mood_analyses")
    op.drop_table("mood_analyses")
