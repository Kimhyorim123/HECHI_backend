"""add book_lists table

Revision ID: d6e5d759c05e
Revises: 5b9120735d1b
Create Date: 2025-12-19 20:07:23.418848

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'd6e5d759c05e'
down_revision: Union[str, None] = '5b9120735d1b'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

def upgrade() -> None:
    op.create_table(
        'book_lists',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('isbn', sa.String(length=13), nullable=False),
        sa.Column('list_type', sa.String(length=50), nullable=False),
        sa.Column('rank', sa.Integer(), nullable=False),
        sa.Column('list_date', sa.Date(), nullable=False),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.ForeignKeyConstraint(['isbn'], ['books.isbn'], ondelete='CASCADE'),
        sa.UniqueConstraint('isbn', 'list_type', 'list_date', name='uq_booklist_isbn_type_date')
    )

def downgrade() -> None:
    op.drop_table('book_lists')
