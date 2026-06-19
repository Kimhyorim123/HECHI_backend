"""expand notification types

Revision ID: 20260601_expand_notification_types
Revises: 20260527_add_book_reading_summaries
Create Date: 2026-06-01
"""

from alembic import op


revision = "20260601_expand_notification_types"
down_revision = "20260527_add_book_reading_summaries"
branch_labels = None
depends_on = None


NEW_ENUM = """ENUM(
    'AI_SUMMARY_READY',
    'GROUP_NOTICE',
    'GENERAL',
    'BADGE_EARNED',
    'BOOK_RECOMMEND',
    'READING_REPORT',
    'READING_SLUMP',
    'REVIEW_REACTION',
    'COLLECTION_REACTION',
    'GROUP_ANNOUNCEMENT',
    'GROUP_MISSION_UPDATE',
    'GROUP_DISCUSSION',
    'SOCIAL_LIKE',
    'SOCIAL_COMMENT',
    'CUSTOMER_SERVICE_ANSWERED'
)"""

OLD_ENUM = """ENUM(
    'AI_SUMMARY_READY',
    'GROUP_NOTICE',
    'GENERAL',
    'BADGE_EARNED',
    'BOOK_RECOMMEND',
    'GROUP_ANNOUNCEMENT',
    'GROUP_MISSION_UPDATE',
    'SOCIAL_LIKE',
    'SOCIAL_COMMENT',
    'CUSTOMER_SERVICE_ANSWERED'
)"""


def upgrade() -> None:
    op.execute(f"ALTER TABLE notifications MODIFY COLUMN type {NEW_ENUM} NOT NULL")


def downgrade() -> None:
    op.execute(f"ALTER TABLE notifications MODIFY COLUMN type {OLD_ENUM} NOT NULL")
