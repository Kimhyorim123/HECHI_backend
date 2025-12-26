"""add published_date and language columns to books

Revision ID: add_published_language_20251126
Revises: 5b9120735d1b
Create Date: 2025-11-26
"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'add_published_language_20251126'
down_revision = '5b9120735d1b'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('books', sa.Column('published_date', sa.Date(), nullable=True))
    op.add_column('books', sa.Column('language', sa.String(length=50), nullable=True))


def downgrade():
    op.drop_column('books', 'language')
    op.drop_column('books', 'published_date')
