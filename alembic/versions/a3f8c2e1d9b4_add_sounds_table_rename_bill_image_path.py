"""add sounds table and rename bill_image_path to bill_image_url

Revision ID: a3f8c2e1d9b4
Revises: 0179de7757ca
Create Date: 2026-06-11 00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "a3f8c2e1d9b4"
down_revision: Union[str, None] = "0179de7757ca"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "sounds",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("category", sa.String(length=64), nullable=False),
        sa.Column("cloudinary_public_id", sa.String(length=255), nullable=False),
        sa.Column("audio_url", sa.Text(), nullable=False),
        sa.Column("duration_seconds", sa.Integer(), nullable=True),
        sa.Column("sort_order", sa.Integer(), server_default="0", nullable=False),
        sa.Column("is_published", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("cloudinary_public_id"),
    )

    op.alter_column("subscriptions", "bill_image_path", new_column_name="bill_image_url")


def downgrade() -> None:
    op.alter_column("subscriptions", "bill_image_url", new_column_name="bill_image_path")
    op.drop_table("sounds")
