"""merge support ticket and google ratings heads

Revision ID: 798502d6d021
Revises: st_created_at_default_20251128, 20251129_add_google_ratings
Create Date: 2025-12-12 16:10:31.210971

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '798502d6d021'
down_revision: Union[str, None] = 'st_created_at_default_20251128'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
