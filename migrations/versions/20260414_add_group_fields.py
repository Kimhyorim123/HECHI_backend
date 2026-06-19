"""add group fields for group creation

Revision ID: 20260414_add_group_fields
Revises: 20260329_add_email_verification_to_users
Create Date: 2026-04-14 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "20260414_add_group_fields"
down_revision = "20260329_add_email_verification_to_users"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("groups", sa.Column("group_id", sa.String(length=50), nullable=True))
    op.add_column("groups", sa.Column("background_image", sa.String(length=512), nullable=True))
    op.add_column("groups", sa.Column("max_members", sa.Integer(), nullable=True))
    op.add_column("groups", sa.Column("description", sa.Text(), nullable=True))
    op.add_column("groups", sa.Column("password_hash", sa.String(length=255), nullable=True))
    with op.batch_alter_table("groups") as batch_op:
        batch_op.create_unique_constraint("uq_groups_group_id", ["group_id"])


def downgrade():
    with op.batch_alter_table("groups") as batch_op:
        batch_op.drop_constraint("uq_groups_group_id", type_="unique")
        batch_op.drop_column("password_hash")
        batch_op.drop_column("description")
        batch_op.drop_column("max_members")
        batch_op.drop_column("background_image")
        batch_op.drop_column("group_id")
