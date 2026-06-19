"""add group post records

Revision ID: 20260601_add_group_post_records
Revises: 20260601_expand_notification_types
Create Date: 2026-06-01
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql


revision = "20260601_add_group_post_records"
down_revision = "20260601_expand_notification_types"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('group_posts', sa.Column('records', mysql.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column('group_posts', 'records')
