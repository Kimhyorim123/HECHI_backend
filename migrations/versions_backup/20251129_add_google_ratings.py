"""
Alembic migration: add Google Books rating fields to books

Revision ID: 20251129_add_google_ratings
Revises: 20251129_add_unique_on_books
Create Date: 2025-11-29
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "20251129_add_google_ratings"
down_revision = "20251129_add_unique_on_books"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("books", sa.Column("google_rating", sa.Float(), nullable=True))
    op.add_column("books", sa.Column("google_ratings_count", sa.Integer(), nullable=True))


def downgrade():
    op.drop_column("books", "google_ratings_count")
    op.drop_column("books", "google_rating")
