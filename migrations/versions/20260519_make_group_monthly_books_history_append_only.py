"""make group monthly books history append only

Revision ID: 20260519_make_group_monthly_books_history_append_only
Revises: 20260517_add_collections
Create Date: 2026-05-19
"""

from alembic import op
import sqlalchemy as sa


revision = "20260519_make_group_monthly_books_history_append_only"
down_revision = "20260517_add_collections"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index(
        "ix_group_monthly_books_group_id",
        "group_monthly_books",
        ["group_id"],
        unique=False,
    )
    op.create_index(
        "ix_group_monthly_books_book_id",
        "group_monthly_books",
        ["book_id"],
        unique=False,
    )
    op.execute("ALTER TABLE group_monthly_books DROP PRIMARY KEY")
    op.execute(
        "ALTER TABLE group_monthly_books "
        "ADD COLUMN id INT NOT NULL AUTO_INCREMENT PRIMARY KEY FIRST"
    )
    op.add_column(
        "group_monthly_books",
        sa.Column(
            "created_at",
            sa.DateTime(),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_column("group_monthly_books", "created_at")
    op.execute("ALTER TABLE group_monthly_books DROP PRIMARY KEY")
    op.execute("ALTER TABLE group_monthly_books DROP COLUMN id")
    op.execute(
        "ALTER TABLE group_monthly_books "
        "ADD PRIMARY KEY (group_id, book_id)"
    )
    op.drop_index("ix_group_monthly_books_book_id", table_name="group_monthly_books")
    op.drop_index("ix_group_monthly_books_group_id", table_name="group_monthly_books")
