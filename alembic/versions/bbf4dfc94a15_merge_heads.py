"""merge_heads

Revision ID: bbf4dfc94a15
Revises: b2c3d4e5f6g7, ff02973421fc
Create Date: 2026-01-18 14:37:03.154774

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'bbf4dfc94a15'
down_revision: Union[str, Sequence[str], None] = ('b2c3d4e5f6g7', 'ff02973421fc')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
