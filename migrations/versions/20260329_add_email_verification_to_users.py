"""add email verification fields to users

Revision ID: 20260329_add_email_verification_to_users
Revises: 20260325_add_login_id_to_users
Create Date: 2026-03-29 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "20260329_add_email_verification_to_users"
down_revision = "20260325_add_login_id_to_users"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("users", sa.Column("email_verified", sa.Boolean(), nullable=True))
    op.add_column("users", sa.Column("email_verification_code_hash", sa.String(length=255), nullable=True))
    op.add_column("users", sa.Column("email_verification_expires_at", sa.DateTime(), nullable=True))
    op.add_column("users", sa.Column("email_verification_sent_at", sa.DateTime(), nullable=True))
    op.add_column("users", sa.Column("email_verified_at", sa.DateTime(), nullable=True))
    op.execute("UPDATE users SET email_verified = 1, email_verified_at = NOW() WHERE email_verified IS NULL")
    with op.batch_alter_table("users") as batch_op:
        batch_op.alter_column("email_verified", existing_type=sa.Boolean(), nullable=False)


def downgrade():
    with op.batch_alter_table("users") as batch_op:
        batch_op.drop_column("email_verified_at")
        batch_op.drop_column("email_verification_sent_at")
        batch_op.drop_column("email_verification_expires_at")
        batch_op.drop_column("email_verification_code_hash")
        batch_op.drop_column("email_verified")
