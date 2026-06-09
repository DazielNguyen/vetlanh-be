"""add_admin_table_indexes

Revision ID: 4cc2489108fb
Revises: ec8731597c38
Create Date: 2026-06-08 16:53:26.914228

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '4cc2489108fb'
down_revision: Union[str, Sequence[str], None] = 'ec8731597c38'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # These indexes may already exist (created by ec8731597c38). IF NOT EXISTS makes this idempotent.
    op.execute("CREATE INDEX IF NOT EXISTS ix_system_errors_status ON system_errors (status)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_subscriptions_user_id ON subscriptions (user_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_subscriptions_status_granted_at ON subscriptions (status, granted_at)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_subscriptions_status_created_at ON subscriptions (status, created_at)")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_subscriptions_status_created_at")
    op.execute("DROP INDEX IF EXISTS ix_subscriptions_status_granted_at")
    op.execute("DROP INDEX IF EXISTS ix_subscriptions_user_id")
    op.execute("DROP INDEX IF EXISTS ix_system_errors_status")
