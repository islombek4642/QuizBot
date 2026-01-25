"""merge multiple heads

Revision ID: 9ac8c86bb938
Revises: bbf4dfc94a15, c3d4e5f6g7h8
Create Date: 2026-01-25 18:25:21.867225

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '9ac8c86bb938'
down_revision: Union[str, Sequence[str], None] = ('bbf4dfc94a15', 'c3d4e5f6g7h8')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
