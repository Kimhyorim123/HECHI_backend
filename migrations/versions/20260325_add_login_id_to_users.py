"""add login_id to users

Revision ID: 20260325_add_login_id_to_users
Revises: 9c7b1b1a9f23
Create Date: 2026-03-25 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "20260325_add_login_id_to_users"
down_revision = "9c7b1b1a9f23"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("users", sa.Column("login_id", sa.String(length=100), nullable=True))
    op.execute("UPDATE users SET login_id = email WHERE login_id IS NULL")
    with op.batch_alter_table("users") as batch_op:
        batch_op.alter_column("login_id", existing_type=sa.String(length=100), nullable=False)
        batch_op.create_unique_constraint("uq_users_login_id", ["login_id"])


def downgrade():
    with op.batch_alter_table("users") as batch_op:
        batch_op.drop_constraint("uq_users_login_id", type_="unique")
        batch_op.drop_column("login_id")
