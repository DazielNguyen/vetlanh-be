"""add email change fields to users

Revision ID: c5d6e7f8a9b0
Revises: b3c4d5e6f7a8
Create Date: 2026-06-22 00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "c5d6e7f8a9b0"
down_revision: Union[str, None] = "b3c4d5e6f7a8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("users", sa.Column("pending_email", sa.String(255), nullable=True))
    op.add_column("users", sa.Column("email_change_token", sa.String(64), nullable=True))
    op.add_column(
        "users",
        sa.Column("email_change_token_expires_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_users_email_change_token",
        "users",
        ["email_change_token"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("ix_users_email_change_token", table_name="users")
    op.drop_column("users", "email_change_token_expires_at")
    op.drop_column("users", "email_change_token")
    op.drop_column("users", "pending_email")
