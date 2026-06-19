"""add user profile image

Revision ID: 20260604_add_user_profile_image
Revises: 20260601_expand_notification_types
Create Date: 2026-06-04
"""

from alembic import op
import sqlalchemy as sa


revision = "20260604_add_user_profile_image"
down_revision = "20260601_add_group_post_records"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("profile_image_url", sa.String(length=1024), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "profile_image_url")
