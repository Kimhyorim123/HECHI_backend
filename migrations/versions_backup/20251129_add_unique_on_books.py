"""
Alembic migration: add UNIQUE constraints on books.isbn and books.nfc_uid

Revision ID: 20251129_add_unique_on_books
Revises: 20251129_books_enhancements
Create Date: 2025-11-29
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "20251129_add_unique_on_books"
down_revision = "20251129_books_enhancements"
branch_labels = None
depends_on = None


def upgrade():
    # Use batch mode for SQLite compatibility when altering constraints
    with op.batch_alter_table("books", schema=None) as batch_op:
        batch_op.create_unique_constraint("uniq_books_isbn", ["isbn"])  # NULLs allowed, unique on non-null
        batch_op.create_unique_constraint("uniq_books_nfc_uid", ["nfc_uid"])  # NULLs allowed, unique on non-null


def downgrade():
    with op.batch_alter_table("books", schema=None) as batch_op:
        batch_op.drop_constraint("uniq_books_isbn", type_="unique")
        batch_op.drop_constraint("uniq_books_nfc_uid", type_="unique")
