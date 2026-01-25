"""add skipped_count and consecutive_skips to quiz_sessions

Revision ID: c3d4e5f6g7h8
Revises: b2c3d4e5f6g7
Create Date: 2026-01-25 18:20:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'c3d4e5f6g7h8'
down_revision: Union[str, None] = 'b2c3d4e5f6g7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add skipped_count column - tracks total skipped questions
    op.add_column('quiz_sessions', sa.Column('skipped_count', sa.Integer(), server_default='0', nullable=False))
    # Add consecutive_skips column - tracks consecutive skips for 3-strike logic
    op.add_column('quiz_sessions', sa.Column('consecutive_skips', sa.Integer(), server_default='0', nullable=False))


def downgrade() -> None:
    op.drop_column('quiz_sessions', 'consecutive_skips')
    op.drop_column('quiz_sessions', 'skipped_count')
