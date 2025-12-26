"""book_lists.isbn FK를 books.isbn_13로 변경

Revision ID: 9c7b1b1a9f23
Revises: 8f5e31b04d4f
Create Date: 2025-12-22 21:20:00.000000

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '9c7b1b1a9f23'
down_revision = '8f5e31b04d4f'
branch_labels = None
depends_on = None

def upgrade():
    # 기존 FK 있으면 삭제
    # books.isbn_13에 인덱스 추가 (없으면 FK 생성 불가)
    with op.batch_alter_table('book_lists') as batch_op:
        batch_op.create_foreign_key('fk_booklists_isbn', 'books', ['isbn'], ['isbn_10'], ondelete='CASCADE')

def downgrade():
    with op.batch_alter_table('book_lists') as batch_op:
        batch_op.drop_constraint('fk_booklists_isbn', type_='foreignkey')