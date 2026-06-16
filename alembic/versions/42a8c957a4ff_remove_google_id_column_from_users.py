"""remove google_id column from users

Revision ID: 42a8c957a4ff
Revises: a3f8c2e1d9b4
Create Date: 2026-06-16 10:32:44.004691

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '42a8c957a4ff'
down_revision: Union[str, Sequence[str], None] = 'a3f8c2e1d9b4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_constraint('users_google_id_key', 'users', type_='unique')
    op.drop_column('users', 'google_id')


def downgrade() -> None:
    op.add_column('users', sa.Column('google_id', sa.VARCHAR(length=128), autoincrement=False, nullable=True))
    op.create_unique_constraint('users_google_id_key', 'users', ['google_id'])
