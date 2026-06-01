"""add_sentiment_to_messages

Revision ID: b1c2d3e4f5a6
Revises: 932e1baaaf4a
Create Date: 2026-06-01 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "b1c2d3e4f5a6"
down_revision: Union[str, None] = "932e1baaaf4a"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "messages",
        sa.Column("sentiment", sa.String(length=10), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("messages", "sentiment")
