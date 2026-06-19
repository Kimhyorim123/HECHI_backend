import argparse
import os
import time
from typing import Optional

import requests
from dotenv import load_dotenv

from app.database import SessionLocal
from app.models import Book


LOOKUP_URL = "https://www.aladin.co.kr/ttb/api/ItemLookUp.aspx"


def get_api_key() -> Optional[str]:
    if os.getenv("ALADIN_API_KEY"):
        return os.getenv("ALADIN_API_KEY")

    for env_path in ("/app/.env", os.path.join(os.getcwd(), ".env")):
        if os.path.exists(env_path):
            load_dotenv(env_path)
    return os.getenv("ALADIN_API_KEY")


def fetch_total_pages(api_key: str, *, isbn13: Optional[str], isbn10: Optional[str]) -> Optional[int]:
    candidates = []
    if isbn13:
        candidates.append(("ISBN13", isbn13))
    if isbn10:
        candidates.append(("ISBN", isbn10))

    for item_id_type, item_id in candidates:
        params = {
            "ttbkey": api_key,
            "itemIdType": item_id_type,
            "ItemId": item_id,
            "output": "js",
            "Version": "20131101",
            "OptResult": "authors,subInfo",
        }
        response = requests.get(LOOKUP_URL, params=params, timeout=20)
        response.raise_for_status()
        item = (response.json().get("item") or [{}])[0]
        sub_info = item.get("subInfo") or {}
        page = sub_info.get("itemPage")
        if page is None:
            continue
        try:
            return int(page)
        except (TypeError, ValueError):
            continue

    return None


def main() -> None:
    parser = argparse.ArgumentParser(description="Backfill Book.total_pages from Aladin ItemLookUp")
    parser.add_argument("--limit", type=int, default=None, help="Maximum number of books to process")
    parser.add_argument("--sleep", type=float, default=0.15, help="Sleep seconds between API requests")
    parser.add_argument("--all", action="store_true", help="Process all books instead of only NULL total_pages")
    parser.add_argument("--dry-run", action="store_true", help="Print matched pages without writing DB")
    parser.add_argument("--log-every", type=int, default=25, help="Print progress every N successful updates")
    args = parser.parse_args()

    api_key = get_api_key()
    if not api_key:
        raise RuntimeError("ALADIN_API_KEY is not set")

    session = SessionLocal()
    try:
        query = session.query(Book).order_by(Book.id.asc())
        if not args.all:
            query = query.filter(Book.total_pages.is_(None))
        if args.limit:
            query = query.limit(args.limit)
        books = query.all()

        updated = 0
        missing = 0
        skipped = 0

        for idx, book in enumerate(books, start=1):
            if not book.isbn_13 and not book.isbn_10:
                skipped += 1
                continue

            try:
                total_pages = fetch_total_pages(
                    api_key,
                    isbn13=book.isbn_13,
                    isbn10=book.isbn_10,
                )
            except Exception as exc:
                print(f"[ERROR] book_id={book.id} title={book.title!r}: {exc}")
                continue

            if total_pages is None:
                missing += 1
                print(f"[MISS] {idx}/{len(books)} book_id={book.id} title={book.title!r}")
            else:
                updated += 1
                if idx == 1 or idx == len(books) or updated % max(args.log_every, 1) == 0:
                    print(
                        f"[OK] {idx}/{len(books)} book_id={book.id} "
                        f"title={book.title!r} total_pages={total_pages}"
                    )
                if not args.dry_run:
                    book.total_pages = total_pages
                    session.add(book)
                    session.commit()

            if args.sleep > 0:
                time.sleep(args.sleep)

        print(
            f"[DONE] processed={len(books)} updated={updated} missing={missing} skipped={skipped} "
            f"dry_run={args.dry_run}"
        )
    finally:
        session.close()


if __name__ == "__main__":
    main()
