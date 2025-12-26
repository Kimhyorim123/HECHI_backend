"""rename isbn to isbn_10 in books

Revision ID: febf3828a747
Revises: 646bcdc64a55
Create Date: 2025-12-22 21:01:55.328874

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql

# revision identifiers, used by Alembic.
revision: str = 'febf3828a747'
down_revision: Union[str, None] = '646bcdc64a55'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # books 테이블의 isbn 컬럼명을 isbn_10으로 변경
    op.alter_column('books', 'isbn', new_column_name='isbn_10', existing_type=sa.String(length=13))
    # ### end Alembic commands ###


def downgrade() -> None:
    # books 테이블의 isbn_10 컬럼명을 isbn으로 복구
    op.alter_column('books', 'isbn_10', new_column_name='isbn', existing_type=sa.String(length=13))
    # ### end Alembic commands ###
