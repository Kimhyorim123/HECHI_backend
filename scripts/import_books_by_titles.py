import sys
import re
from typing import List, Optional
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.database import SessionLocal
from app.models import Book, Author, BookAuthor, BookCategory
from app.services.google_books import get_client, map_volume_to_book_fields


def pick_best_volume(vols: List[dict], prefer_lang: Optional[str] = None) -> Optional[dict]:
    if not vols:
        return None
    if prefer_lang:
        for v in vols:
            lang = (v.get("volumeInfo", {}) or {}).get("language")
            if (lang or "").lower() == prefer_lang.lower():
                return v
    return vols[0]


def upsert_book_from_fields(db: Session, fields: dict) -> Optional[Book]:
    title = (fields.get("title") or "").strip()
    if not title:
        return None
    isbn = fields.get("isbn")
    book = None
    if isbn:
        book = db.query(Book).filter(Book.isbn == isbn).first()
    if not book:
        # fallback by title+publisher match (case-insensitive)
        q = db.query(Book).filter(func.lower(Book.title) == title.lower())
        pub = fields.get("publisher")
        if pub:
            q = q.filter(func.lower(Book.publisher) == pub.lower())
        book = q.first()

    if not book:
        book = Book(
            isbn=isbn,
            title=title,
            publisher=fields.get("publisher"),
            published_date=fields.get("published_date"),
            language=fields.get("language"),
            category=fields.get("category"),
            total_pages=fields.get("total_pages"),
            thumbnail=fields.get("thumbnail"),
            small_thumbnail=fields.get("small_thumbnail"),
            google_rating=fields.get("google_rating"),
            google_ratings_count=fields.get("google_ratings_count"),
        )
        db.add(book)
        db.flush()
    else:
        # update missing thumbnails/ratings if available
        if not getattr(book, "thumbnail", None) and fields.get("thumbnail"):
            book.thumbnail = fields["thumbnail"]
        if not getattr(book, "small_thumbnail", None) and fields.get("small_thumbnail"):
            book.small_thumbnail = fields["small_thumbnail"]
        if fields.get("google_rating") is not None:
            book.google_rating = fields["google_rating"]
        if fields.get("google_ratings_count") is not None:
            book.google_ratings_count = fields["google_ratings_count"]
        if not getattr(book, "language", None) and fields.get("language"):
            book.language = fields["language"]
        if not getattr(book, "category", None) and fields.get("category"):
            book.category = fields["category"]

    # Categories (many-to-many via BookCategory)
    for cname in fields.get("categories", []) or []:
        cname = cname.strip()
        if not cname:
            continue
        exists = (
            db.query(BookCategory)
            .filter(BookCategory.book_id == book.id, BookCategory.category_name == cname)
            .first()
        )
        if not exists:
            db.add(BookCategory(book_id=book.id, category_name=cname))

    # Authors
    for name in fields.get("authors", []) or []:
        name = name.strip()
        if not name:
            continue
        a = db.query(Author).filter(func.lower(Author.name) == name.lower()).first()
        if not a:
            a = Author(name=name)
            db.add(a)
            db.flush()
        link = db.query(BookAuthor).filter(BookAuthor.book_id == book.id, BookAuthor.author_id == a.id).first()
        if not link:
            db.add(BookAuthor(book_id=book.id, author_id=a.id))

    return book


def import_by_titles(titles: List[str], prefer_lang: Optional[str] = "ko") -> List[int]:
    client = get_client()
    db = SessionLocal()
    try:
        added_ids: List[int] = []
        for raw in titles:
            q = raw.strip()
            if not q:
                continue
            # Prefer exact title search
            query = f'intitle:"{q}"'
            vols = client.by_query(query, max_results=5)
            vol = pick_best_volume(vols, prefer_lang=prefer_lang)
            if not vol:
                # fallback simple query
                vols = client.by_query(q, max_results=5)
                vol = pick_best_volume(vols, prefer_lang=prefer_lang)
            if not vol:
                print(f"No result: {q}")
                continue
            fields = map_volume_to_book_fields(vol)
            book = upsert_book_from_fields(db, fields)
            db.commit()
            if book:
                added_ids.append(book.id)
                print(f"Imported: {q} -> book_id={book.id}")
        return added_ids
    finally:
        db.close()


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python scripts/import_books_by_titles.py 'title1/title2/...' ")
        sys.exit(1)
    raw = sys.argv[1]
    titles = [t.strip() for t in raw.split('/')]
    ids = import_by_titles(titles)
    print("Done. IDs:", ids)
