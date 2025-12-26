revision = '20251221_change_created_date_to_datetime'
down_revision = 'd6e5d759c05e'
branch_labels = None
depends_on = None
"""
Migration: Change created_date to DateTime in bookmarks, highlights, notes
"""
from alembic import op
import sqlalchemy as sa

def upgrade():
    op.alter_column('bookmarks', 'created_date', type_=sa.DateTime(), existing_type=sa.Date(), nullable=False)
    op.alter_column('highlights', 'created_date', type_=sa.DateTime(), existing_type=sa.Date(), nullable=False)
    op.alter_column('notes', 'created_date', type_=sa.DateTime(), existing_type=sa.Date(), nullable=False)

def downgrade():
    op.alter_column('bookmarks', 'created_date', type_=sa.Date(), existing_type=sa.DateTime(), nullable=False)
    op.alter_column('highlights', 'created_date', type_=sa.Date(), existing_type=sa.DateTime(), nullable=False)
    op.alter_column('notes', 'created_date', type_=sa.Date(), existing_type=sa.DateTime(), nullable=False)
