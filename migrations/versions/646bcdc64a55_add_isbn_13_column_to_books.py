"""add isbn_13 column to books

Revision ID: 646bcdc64a55
Revises: dacacada880f
Create Date: 2025-12-22 20:59:18.282209

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql

# revision identifiers, used by Alembic.
revision: str = '646bcdc64a55'
down_revision: Union[str, None] = 'dacacada880f'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # books 테이블에 isbn_13 컬럼 추가
    op.add_column('books', sa.Column('isbn_13', sa.String(length=13), nullable=True))
    # ### end Alembic commands ###


def downgrade() -> None:
    # books 테이블에서 isbn_13 컬럼 제거
    op.drop_column('books', 'isbn_13')
    # ### end Alembic commands ###
