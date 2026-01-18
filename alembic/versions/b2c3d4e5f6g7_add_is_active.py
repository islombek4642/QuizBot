"""add is_active to user and group

Revision ID: b2c3d4e5f6g7
Revises: a1b2c3d4e5f6
Create Date: 2026-01-18 19:30:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'b2c3d4e5f6g7'
down_revision: Union[str, None] = 'a1b2c3d4e5f6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

def upgrade() -> None:
    # Add is_active to users
    op.add_column('users', sa.Column('is_active', sa.Boolean(), server_default='true', nullable=False))
    # Add is_active to groups
    # Note: Adding safe check if groups table exists might be good, 
    # but based on migrate_groups_to_sql.py it should exist.
    op.add_column('groups', sa.Column('is_active', sa.Boolean(), server_default='true', nullable=False))

def downgrade() -> None:
    op.drop_column('groups', 'is_active')
    op.drop_column('users', 'is_active')
