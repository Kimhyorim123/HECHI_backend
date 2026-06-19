"""add badge system

Revision ID: 20260524_add_badge_system
Revises: 20260523_add_notification_center
Create Date: 2026-05-24
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql


revision = '20260524_add_badge_system'
down_revision = '20260523_add_notification_center'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'badge_definitions',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('code', sa.String(length=100), nullable=False),
        sa.Column('category', sa.String(length=50), nullable=False),
        sa.Column('level_code', sa.String(length=100), nullable=False),
        sa.Column('title', sa.String(length=255), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('threshold', sa.Integer(), nullable=False),
        sa.Column('icon_url', sa.String(length=1024), nullable=True),
        sa.Column('context_type', sa.String(length=50), nullable=True),
        sa.Column('is_repeatable', sa.Boolean(), nullable=False, server_default=sa.text('0')),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('code', name='uq_badge_definition_code'),
    )
    op.create_table(
        'user_badges',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('badge_definition_id', sa.Integer(), nullable=False),
        sa.Column('context_value', sa.String(length=191), nullable=True),
        sa.Column('progress_snapshot', mysql.JSON(), nullable=True),
        sa.Column('earned_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['badge_definition_id'], ['badge_definitions.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('user_id', 'badge_definition_id', 'context_value', name='uq_user_badge_context'),
    )
    op.create_index('ix_user_badges_user_id', 'user_badges', ['user_id'], unique=False)


def downgrade() -> None:
    op.drop_index('ix_user_badges_user_id', table_name='user_badges')
    op.drop_table('user_badges')
    op.drop_table('badge_definitions')
