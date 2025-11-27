"""add faqs and support_tickets

Revision ID: add_support_tables_20251126
Revises: add_ranking_tables_20251126
Create Date: 2025-11-26
"""

from alembic import op
import sqlalchemy as sa

revision = 'add_support_tables_20251126'
down_revision = 'add_ranking_tables_20251126'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'faqs',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('question', sa.String(length=255), nullable=False),
        sa.Column('answer', sa.Text(), nullable=False),
        sa.Column('is_pinned', sa.Boolean(), nullable=False, server_default=sa.text('1')),
    )
    op.create_table(
        'support_tickets',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('title', sa.String(length=255), nullable=False),
        sa.Column('description', sa.Text(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('status', sa.String(length=20), nullable=False, server_default='open'),
    )


def downgrade():
    op.drop_table('support_tickets')
    op.drop_table('faqs')
