"""add search_history, wishlist, book_views

Revision ID: add_ranking_tables_20251126
Revises: add_published_language_20251126
Create Date: 2025-11-26
"""

from alembic import op
import sqlalchemy as sa

revision = 'add_ranking_tables_20251126'
down_revision = 'add_published_language_20251126'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'search_history',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('user_id', sa.Integer(), nullable=True),
        sa.Column('query', sa.String(length=255), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
    )
    op.create_table(
        'wishlist',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('book_id', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
    )
    op.create_unique_constraint('uq_wishlist_user_book', 'wishlist', ['user_id', 'book_id'])
    op.create_table(
        'book_views',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('book_id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
    )


def downgrade():
    op.drop_table('book_views')
    op.drop_constraint('uq_wishlist_user_book', 'wishlist', type_='unique')
    op.drop_table('wishlist')
    op.drop_table('search_history')
