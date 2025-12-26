"""
Revision ID: add_book_description
Revises: xxxxxx
Create Date: 2025-12-21
"""

revision = 'add_book_description'
down_revision = '20251221_change_created_date_to_datetime'
branch_labels = None
depends_on = None
from alembic import op
import sqlalchemy as sa

def upgrade():
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    columns = [col['name'] for col in inspector.get_columns('books')]
    if 'description' not in columns:
        op.add_column('books', sa.Column('description', sa.Text(), nullable=True))

def downgrade():
    op.drop_column('books', 'description')
