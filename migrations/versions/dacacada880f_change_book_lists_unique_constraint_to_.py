"""Change book_lists unique constraint to (isbn, list_type) only

Revision ID: dacacada880f
Revises: add_book_description
Create Date: 2025-12-22 20:12:35.478266

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql

# revision identifiers, used by Alembic.
revision: str = 'dacacada880f'
down_revision: Union[str, None] = 'add_book_description'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 기존 유니크 인덱스 삭제
    # 이미 직접 인덱스를 삭제했으므로, alembic에서 중복 삭제를 방지
    # op.drop_index('uq_booklist_isbn_type_date', table_name='book_lists')
    # 새로운 유니크 인덱스 생성
    # 이미 직접 인덱스를 생성했으므로, alembic에서 중복 생성을 방지
    # op.create_index('uq_booklist_isbn_type', 'book_lists', ['isbn', 'list_type'], unique=True)
    # ### end Alembic commands ###
    pass


def downgrade() -> None:
    # 롤백 시 (isbn, list_type) 인덱스 삭제, (isbn, list_type, list_date) 인덱스 복구
    # 이미 직접 인덱스를 조작했으므로, alembic에서 중복 조작을 방지
    # op.drop_index('uq_booklist_isbn_type', table_name='book_lists')
    # op.create_index('uq_booklist_isbn_type_date', 'book_lists', ['isbn', 'list_type', 'list_date'], unique=True)
    # ### end Alembic commands ###
    pass
