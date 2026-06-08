"""add_admin_tables_subscriptions_system_errors

Revision ID: ec8731597c38
Revises: c4d5e6f7a8b9
Create Date: 2026-06-08 16:48:48.545093

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'ec8731597c38'
down_revision: Union[str, Sequence[str], None] = 'c4d5e6f7a8b9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "system_errors",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("timestamp", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("error_type", sa.String(length=100), nullable=False),
        sa.Column("route", sa.String(length=500), nullable=True),
        sa.Column("severity", sa.String(length=10), server_default="HIGH", nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=20), server_default="open", nullable=False),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_system_errors_status", "system_errors", ["status"])

    op.create_table(
        "subscriptions",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=20), server_default="pending", nullable=False),
        sa.Column("plan_name", sa.String(length=100), nullable=True),
        sa.Column("duration_months", sa.Integer(), nullable=True),
        sa.Column("amount_vnd", sa.Integer(), nullable=True),
        sa.Column("transfer_date", sa.DateTime(timezone=True), nullable=True),
        sa.Column("transfer_note", sa.Text(), nullable=True),
        sa.Column("granted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("rejected_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_subscriptions_user_id", "subscriptions", ["user_id"])
    op.create_index("ix_subscriptions_status_granted_at", "subscriptions", ["status", "granted_at"])
    op.create_index("ix_subscriptions_status_created_at", "subscriptions", ["status", "created_at"])

    # Add missing columns on users — safe to run on a DB that already has them
    # because we check information_schema first.
    conn = op.get_bind()
    existing = {
        row[0]
        for row in conn.execute(
            sa.text("SELECT column_name FROM information_schema.columns WHERE table_name='users'")
        )
    }
    if "account_type" not in existing:
        op.add_column("users", sa.Column("account_type", sa.String(length=20), server_default="email", nullable=True))
    if "last_active_at" not in existing:
        op.add_column("users", sa.Column("last_active_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_subscriptions_status_created_at")
    op.execute("DROP INDEX IF EXISTS ix_subscriptions_status_granted_at")
    op.execute("DROP INDEX IF EXISTS ix_subscriptions_user_id")
    op.drop_table("subscriptions")
    op.execute("DROP INDEX IF EXISTS ix_system_errors_status")
    op.drop_table("system_errors")
    op.drop_column("users", "last_active_at")
    op.drop_column("users", "account_type")
