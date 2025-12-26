#!/usr/bin/env python3
"""Cleanup books without cover thumbnails and prune orphan authors.

Dry-run by default: pass --apply to actually delete.
Criteria: BOTH thumbnail and small_thumbnail are NULL (strict). Adjust if needed.
"""
import argparse
from sqlalchemy import create_engine, func
from sqlalchemy.orm import Session
from app.core.config import get_settings
from app.models import Book, Author, BookAuthor


def get_engine(override_url: str | None):
    if override_url:
        return create_engine(override_url, pool_pre_ping=True)
    settings = get_settings()
    return create_engine(settings.database_url, pool_pre_ping=True)


def find_books_no_cover(session: Session):
    return (
        session.query(Book)
        .filter(Book.thumbnail.is_(None), Book.small_thumbnail.is_(None))
        .all()
    )


def delete_books(session: Session, books):
    for b in books:
        session.delete(b)


def prune_orphan_authors(session: Session):
    # Authors with zero remaining BookAuthor links
    orphan_authors = (
        session.query(Author)
        .outerjoin(BookAuthor, BookAuthor.author_id == Author.id)
        .group_by(Author.id)
        .having(func.count(BookAuthor.book_id) == 0)
        .all()
    )
    for a in orphan_authors:
        session.delete(a)
    return len(orphan_authors)


def main(apply: bool, db_url: str | None):
    engine = get_engine(db_url)
    with Session(engine) as session:
        books = find_books_no_cover(session)
        book_count = len(books)
        # Count orphan authors BEFORE deletion (since deleting books may create more orphans)
        initial_orphans = (
            session.query(Author)
            .outerjoin(BookAuthor, BookAuthor.author_id == Author.id)
            .group_by(Author.id)
            .having(func.count(BookAuthor.book_id) == 0)
            .count()
        )
        print(f"Found {book_count} books without cover (thumbnail & small_thumbnail both NULL).")
        print(f"Existing orphan authors before deletion: {initial_orphans}")
        if not apply:
            print("Dry-run: no changes applied. Use --apply to perform deletion.")
            return
        # Perform deletions
        delete_books(session, books)
        session.flush()  # ensure cascades applied
        pruned = prune_orphan_authors(session)
        session.commit()
        print(f"Deleted {book_count} books. Pruned {pruned} orphan authors.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Cleanup no-cover books and prune orphan authors.")
    parser.add_argument("--apply", action="store_true", help="Apply deletions (omit for dry-run)")
    parser.add_argument("--database-url", dest="db_url", help="Override database URL (optional)")
    args = parser.parse_args()
    main(args.apply, args.db_url)
