"""add wellness_checklist_completions table

Revision ID: c4d5e6f7a8b9
Revises: a1b2c3d4e5f6
Create Date: 2026-06-07 10:00:00.000000
"""

import sqlalchemy as sa
from alembic import op

revision = "c4d5e6f7a8b9"
down_revision = "a1b2c3d4e5f6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "wellness_checklist_completions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("item_key", sa.String(50), nullable=False),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "item_key", "date", name="uq_wellness_user_item_date"),
    )
    op.create_index(
        "ix_wellness_checklist_completions_user_id",
        "wellness_checklist_completions",
        ["user_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_wellness_checklist_completions_user_id", table_name="wellness_checklist_completions")
    op.drop_table("wellness_checklist_completions")
