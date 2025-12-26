"""add default for support_tickets.created_at

Revision ID: st_created_at_default_20251128
Revises: add_support_tables_20251126
Create Date: 2025-11-28
"""

from alembic import op
import sqlalchemy as sa

revision = 'st_created_at_default_20251128'
down_revision = 'add_support_tables_20251126'
branch_labels = None
depends_on = None


def upgrade():
    # Use batch_alter_table for SQLite/PostgreSQL compatibility to add default
    with op.batch_alter_table('support_tickets', schema=None) as batch_op:
        batch_op.alter_column(
            'created_at',
            existing_type=sa.DateTime(),
            existing_nullable=False,
            server_default=sa.text('CURRENT_TIMESTAMP')
        )


def downgrade():
    with op.batch_alter_table('support_tickets', schema=None) as batch_op:
        batch_op.alter_column(
            'created_at',
            existing_type=sa.DateTime(),
            existing_nullable=False,
            server_default=None
        )
