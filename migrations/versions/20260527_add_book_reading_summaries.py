"""add book reading summaries

Revision ID: 20260527_add_book_reading_summaries
Revises: 20260524_add_badge_system
Create Date: 2026-05-27
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql


revision = '20260527_add_book_reading_summaries'
down_revision = '20260524_add_badge_system'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'book_reading_summaries',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('book_id', sa.Integer(), nullable=False),
        sa.Column('status', sa.Enum('NOT_READY', 'PENDING', 'PROCESSING', 'READY', 'FAILED', name='readingsummarystatus'), nullable=False, server_default='NOT_READY'),
        sa.Column('summary_dirty', sa.Boolean(), nullable=False, server_default=sa.text('0')),
        sa.Column('stats_json', mysql.JSON(), nullable=True),
        sa.Column('summary_json', mysql.JSON(), nullable=True),
        sa.Column('last_source_updated_at', sa.DateTime(), nullable=True),
        sa.Column('last_summarized_at', sa.DateTime(), nullable=True),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['book_id'], ['books.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('user_id', 'book_id', name='uq_book_reading_summary_user_book'),
    )
    op.create_index('ix_book_reading_summaries_user_id', 'book_reading_summaries', ['user_id'], unique=False)
    op.create_index('ix_book_reading_summaries_status', 'book_reading_summaries', ['status'], unique=False)
    op.create_index('ix_book_reading_summaries_dirty_updated', 'book_reading_summaries', ['summary_dirty', 'last_source_updated_at'], unique=False)


def downgrade() -> None:
    op.drop_index('ix_book_reading_summaries_dirty_updated', table_name='book_reading_summaries')
    op.drop_index('ix_book_reading_summaries_status', table_name='book_reading_summaries')
    op.drop_index('ix_book_reading_summaries_user_id', table_name='book_reading_summaries')
    op.drop_table('book_reading_summaries')
