"""add username column, make email nullable

Revision ID: a1b2c3d4e5f6
Revises: b2c3d4e5f6a7
Create Date: 2026-06-05 00:00:00.000000

"""

import sqlalchemy as sa
from alembic import op

revision = "a1b2c3d4e5f6"
down_revision = "b2c3d4e5f6a7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("username", sa.String(50), nullable=True))
    op.create_index("ix_users_username", "users", ["username"], unique=True)
    op.alter_column("users", "email", existing_type=sa.String(255), nullable=True)


def downgrade() -> None:
    # Rows with email=NULL cannot be restored — only safe if no username-only users exist.
    op.alter_column("users", "email", existing_type=sa.String(255), nullable=False)
    op.drop_index("ix_users_username", table_name="users")
    op.drop_column("users", "username")
