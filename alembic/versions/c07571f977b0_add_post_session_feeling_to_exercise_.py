"""add_post_session_feeling_to_exercise_logs

Revision ID: c07571f977b0
Revises: 4cc2489108fb
Create Date: 2026-06-09 01:12:44.798141

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c07571f977b0'
down_revision: Union[str, Sequence[str], None] = '4cc2489108fb'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('user_exercise_logs', sa.Column('post_session_feeling', sa.String(length=20), nullable=True))


def downgrade() -> None:
    op.drop_column('user_exercise_logs', 'post_session_feeling')
