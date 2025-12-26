import os
import time
import argparse
from typing import List

import httpx
from sqlalchemy import select, func
from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.models import Book, BookCategory, Author, BookAuthor
from app.services.google_books import GoogleBooksClient, map_volume_to_book_fields


def need_fetch(session: Session, book_id: int) -> bool:
    author_links = session.execute(
        select(func.count()).select_from(BookAuthor).where(BookAuthor.book_id == book_id)
    ).scalar_one()
    cat_links = session.execute(
        select(func.count()).select_from(BookCategory).where(BookCategory.book_id == book_id)
    ).scalar_one()
    return (author_links == 0) or (cat_links == 0)


def ensure_authors(session: Session, book_id: int, names: List[str]) -> None:
    for name in names:
        a = session.execute(select(Author).where(Author.name == name)).scalar_one_or_none()
        if not a:
            a = Author(name=name)
            session.add(a)
            session.flush()
        link = session.execute(
            select(BookAuthor).where(BookAuthor.book_id == book_id, BookAuthor.author_id == a.id)
        ).scalar_one_or_none()
        if not link:
            session.add(BookAuthor(book_id=book_id, author_id=a.id))


def ensure_categories(session: Session, book_id: int, cats: List[str]) -> None:
    for c in cats:
        exist = session.execute(
            select(BookCategory).where(
                BookCategory.book_id == book_id, BookCategory.category_name == c
            )
        ).scalar_one_or_none()
        if not exist:
            session.add(BookCategory(book_id=book_id, category_name=c))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--start-id", type=int, default=0, help="Start from book id (exclusive)")
    parser.add_argument("--limit", type=int, default=0, help="Max books to process (0=all)")
    parser.add_argument("--sleep", type=float, default=2.0, help="Sleep seconds between API calls")
    parser.add_argument("--retries", type=int, default=3, help="Max retries on 429")
    parser.add_argument("--only-missing", action="store_true", help="Only fetch when authors or categories missing")
    args = parser.parse_args()

    client = GoogleBooksClient(api_key=os.getenv("GOOGLE_BOOKS_API_KEY"))

    s = SessionLocal()
    processed = 0
    updated = 0
    try:
        books = s.execute(
            select(Book).where(Book.id > args.start_id).order_by(Book.id)
        ).scalars().all()
        for book in books:
            if args.limit and processed >= args.limit:
                break
            processed += 1

            if not book.isbn:
                continue

            if args.only_missing and not need_fetch(s, book.id):
                continue

            attempt = 0
            while True:
                try:
                    vols = client.by_isbn(book.isbn)
                    if not vols:
                        break
                    mapped = map_volume_to_book_fields(vols[0])
                    ensure_authors(s, book.id, mapped.get("authors") or [])
                    ensure_categories(s, book.id, mapped.get("categories") or [])
                    updated += 1
                    time.sleep(args.sleep)
                    break
                except httpx.HTTPStatusError as e:
                    if e.response is not None and e.response.status_code == 429 and attempt < args.retries:
                        backoff = max(args.sleep, 1.0) * (2 ** attempt)
                        time.sleep(backoff)
                        attempt += 1
                        continue
                    else:
                        raise

            if processed % 50 == 0:
                s.commit()
                print(f"Committed at {processed}, updated {updated}")

        s.commit()
        print(f"Done. processed={processed}, updated={updated}")
    finally:
        s.close()


if __name__ == "__main__":
    main()
