"""add group pin and report features

Revision ID: 20260415_add_group_pin_and_reports
Revises: 20260414_add_group_social_tables
Create Date: 2026-04-15 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "20260415_add_group_pin_and_reports"
down_revision = "20260414_add_group_social_tables"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("group_posts", sa.Column("is_pinned", sa.Boolean(), nullable=False, server_default=sa.text("0")))
    op.add_column("group_posts", sa.Column("pinned_at", sa.DateTime(), nullable=True))

    op.create_table(
        "group_post_reports",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("post_id", sa.Integer(), nullable=False),
        sa.Column("reporter_user_id", sa.Integer(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
        sa.ForeignKeyConstraint(["post_id"], ["group_posts.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["reporter_user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("post_id", "reporter_user_id", name="uq_group_post_report_user"),
    )

    op.create_table(
        "group_comment_reports",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("comment_id", sa.Integer(), nullable=False),
        sa.Column("reporter_user_id", sa.Integer(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
        sa.ForeignKeyConstraint(["comment_id"], ["group_comments.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["reporter_user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("comment_id", "reporter_user_id", name="uq_group_comment_report_user"),
    )


def downgrade():
    op.drop_table("group_comment_reports")
    op.drop_table("group_post_reports")
    op.drop_column("group_posts", "pinned_at")
    op.drop_column("group_posts", "is_pinned")
