"""add exercise reminder to notification preferences

Revision ID: b2c3d4e5f6a7
Revises: f1a2b3c4d5e6
Create Date: 2026-06-02 22:50:00.000000
"""

import sqlalchemy as sa
from alembic import op

revision = "b2c3d4e5f6a7"
down_revision = "f1a2b3c4d5e6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "notification_preferences",
        sa.Column("exercise_enabled", sa.Boolean(), nullable=False, server_default="true"),
    )
    op.add_column(
        "notification_preferences",
        sa.Column("exercise_reminder_time", sa.String(5), nullable=False, server_default="08:00"),
    )


def downgrade() -> None:
    op.drop_column("notification_preferences", "exercise_reminder_time")
    op.drop_column("notification_preferences", "exercise_enabled")
