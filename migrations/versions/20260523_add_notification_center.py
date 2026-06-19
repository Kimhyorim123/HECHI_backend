"""add notification center fields and settings

Revision ID: 20260523_add_notification_center
Revises: 20260519_make_group_monthly_books_history_append_only
Create Date: 2026-05-23
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql


revision = '20260523_add_notification_center'
down_revision = '20260519_make_group_monthly_books_history_append_only'
branch_labels = None
depends_on = None


old_notification_type = sa.Enum(
    'AI_SUMMARY_READY',
    'GROUP_NOTICE',
    'GENERAL',
    name='notificationtype',
)
new_notification_type = sa.Enum(
    'AI_SUMMARY_READY',
    'GROUP_NOTICE',
    'GENERAL',
    'BADGE_EARNED',
    'BOOK_RECOMMEND',
    'GROUP_ANNOUNCEMENT',
    'GROUP_MISSION_UPDATE',
    'SOCIAL_LIKE',
    'SOCIAL_COMMENT',
    'CUSTOMER_SERVICE_ANSWERED',
    name='notificationtype',
)
notification_tab_category = sa.Enum(
    'GENERAL',
    'GROUP',
    name='notificationtabcategory',
)


def upgrade() -> None:
    bind = op.get_bind()
    notification_tab_category.create(bind, checkfirst=True)

    with op.batch_alter_table('notifications') as batch_op:
        batch_op.alter_column(
            'type',
            existing_type=old_notification_type,
            type_=new_notification_type,
            existing_nullable=False,
        )
        batch_op.add_column(sa.Column('tab_category', notification_tab_category, nullable=False, server_default='GENERAL'))
        batch_op.add_column(sa.Column('thumbnail_url', sa.String(length=1024), nullable=True))
        batch_op.add_column(sa.Column('target_info', mysql.JSON() if bind.dialect.name == 'mysql' else sa.JSON(), nullable=True))

    op.create_index('ix_notifications_user_created_at', 'notifications', ['user_id', 'created_at'], unique=False)
    op.create_index('ix_notifications_user_is_read', 'notifications', ['user_id', 'is_read'], unique=False)

    op.create_table(
        'user_notification_settings',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('push_enabled', sa.Boolean(), nullable=False, server_default=sa.text('1')),
        sa.Column('general_enabled', sa.Boolean(), nullable=False, server_default=sa.text('1')),
        sa.Column('group_enabled', sa.Boolean(), nullable=False, server_default=sa.text('1')),
        sa.Column('marketing_enabled', sa.Boolean(), nullable=False, server_default=sa.text('0')),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('user_id', name='uq_user_notification_settings_user_id'),
    )

    op.execute(
        sa.text(
            """
            INSERT INTO user_notification_settings (user_id, push_enabled, general_enabled, group_enabled, marketing_enabled)
            SELECT id, 1, 1, 1, 0
            FROM users
            """
        )
    )


def downgrade() -> None:
    op.drop_table('user_notification_settings')
    op.drop_index('ix_notifications_user_is_read', table_name='notifications')
    op.drop_index('ix_notifications_user_created_at', table_name='notifications')

    with op.batch_alter_table('notifications') as batch_op:
        batch_op.drop_column('target_info')
        batch_op.drop_column('thumbnail_url')
        batch_op.drop_column('tab_category')
        batch_op.alter_column(
            'type',
            existing_type=new_notification_type,
            type_=old_notification_type,
            existing_nullable=False,
        )

    bind = op.get_bind()
    notification_tab_category.drop(bind, checkfirst=True)
