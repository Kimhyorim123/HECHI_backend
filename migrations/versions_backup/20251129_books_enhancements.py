"""
Alembic migration: add authors/thumbnail columns, expand category length

Revision ID: 20251129_books_enhancements
Revises: <PUT_PREVIOUS_REVISION_ID>
Create Date: 2025-11-29
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "20251129_books_enhancements"
down_revision = "798502d6d021"
branch_labels = None
depends_on = None


def upgrade():
    # Extend category length to 255 (if smaller before)
    try:
        op.alter_column("books", "category", existing_type=sa.String(length=100), type_=sa.String(length=255), existing_nullable=True)
    except Exception:
        # If existing type unknown/already larger, just ensure column exists
        pass

    # Add authors
    op.add_column("books", sa.Column("authors", sa.String(length=255), nullable=True))

    # Add image link columns
    op.add_column("books", sa.Column("thumbnail", sa.String(length=512), nullable=True))
    op.add_column("books", sa.Column("small_thumbnail", sa.String(length=512), nullable=True))

    # NOTE: Unique constraints for isbn/nfc_uid intentionally omitted here
    # to avoid migration failure when duplicates exist. Apply later after cleanup.


def downgrade():
    # Drop image link columns
    op.drop_column("books", "small_thumbnail")
    op.drop_column("books", "thumbnail")

    # Drop authors
    op.drop_column("books", "authors")

    # Optionally shrink category back (commented, as original size unknown)
    # op.alter_column("books", "category", type_=sa.String(length=100), existing_nullable=True)
