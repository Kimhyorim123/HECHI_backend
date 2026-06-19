"""add group discussion votes

Revision ID: 20260418_add_group_discussion_votes
Revises: 20260415_add_group_pin_and_reports
Create Date: 2026-04-18
"""

from alembic import op
import sqlalchemy as sa


revision = "20260418_add_group_discussion_votes"
down_revision = "20260415_add_group_pin_and_reports"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "group_post_discussion_votes",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("post_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("option_id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["post_id"], ["group_posts.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("post_id", "user_id", name="uq_group_post_discussion_vote_user"),
    )


def downgrade() -> None:
    op.drop_table("group_post_discussion_votes")
