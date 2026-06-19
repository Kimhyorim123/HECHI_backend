"""add group report reason code

Revision ID: 20260418_add_group_report_reason_code
Revises: 20260418_add_group_discussion_votes
Create Date: 2026-04-18
"""

from alembic import op
import sqlalchemy as sa


revision = "20260418_add_group_report_reason_code"
down_revision = "20260418_add_group_discussion_votes"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "group_post_reports",
        sa.Column("reason_code", sa.String(length=50), nullable=False, server_default="OTHER"),
    )
    op.add_column(
        "group_comment_reports",
        sa.Column("reason_code", sa.String(length=50), nullable=False, server_default="OTHER"),
    )
    op.execute("UPDATE group_post_reports SET reason_code = 'OTHER' WHERE reason_code IS NULL OR reason_code = ''")
    op.execute("UPDATE group_comment_reports SET reason_code = 'OTHER' WHERE reason_code IS NULL OR reason_code = ''")


def downgrade() -> None:
    op.drop_column("group_comment_reports", "reason_code")
    op.drop_column("group_post_reports", "reason_code")
