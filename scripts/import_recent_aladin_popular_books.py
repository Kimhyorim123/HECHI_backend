import os
import re
import time
from dataclasses import dataclass
from datetime import date, datetime
from typing import Iterable

import requests
from sqlalchemy import func

from app.database import SessionLocal
from app.models import Author, Book, BookAuthor, BookCategory


ALADIN_API_URL = "https://www.aladin.co.kr/ttb/api/ItemList.aspx"
ALADIN_LOOKUP_URL = "https://www.aladin.co.kr/ttb/api/ItemLookUp.aspx"
ALLOWED_YEARS = {2010, 2011, 2012, 2013, 2014, 2015, 2016, 2017, 2018, 2019, 2020}
MAX_RESULTS_PER_LIST = 30
REQUEST_SLEEP_SECONDS = 0.2

# 추천/메인 화면과 맞춰 장르별 베스트셀러도 같이 적재할 수 있게 사용
GENRE_CATEGORY_IDS = {
    "소설": 1,
    "시": 3,
    "에세이": 55889,
    "만화": 2551,
    "추리": 2553,
    "스릴러/공포": 2555,
    "SF": 2557,
    "판타지": 2557,
    "로맨스": 2559,
    "역사": 74,
    "과학": 987,
    "인문": 656,
    "철학": 51346,
    "사회/정치": 798,
    "경제/경영": 170,
    "자기계발": 336,
}


def _api_key() -> str:
    key = os.getenv("ALADIN_API_KEY")
    if not key:
        raise RuntimeError("ALADIN_API_KEY is not configured")
    return key


def _normalize_title(value: str | None) -> str:
    if not value:
        return ""
    text = value.strip().lower()
    # 판본성 꼬리표는 최대한 제거해서 동일 작품 중복을 줄인다.
    text = re.sub(
        r"\((?:개정판|개정증보판|리커버|양장|반양장|특별판|한정판|포켓판|무선판|개정)\)",
        "",
        text,
        flags=re.IGNORECASE,
    )
    text = re.sub(r"[\s\-_:,.'\"“”‘’!?~·/\\\[\]\(\)]", "", text)
    return text


def _normalize_person_name(value: str) -> str:
    text = re.sub(r"\s*\([^)]*\)", "", value or "")
    text = re.sub(r"\s+", "", text).strip().lower()
    return text


def _parse_author_names(raw_author: str | None) -> list[str]:
    if not raw_author:
        return []
    names: list[str] = []
    for part in raw_author.split(","):
        normalized = _normalize_person_name(part)
        if normalized:
            names.append(normalized)
    # 순서 보존 중복 제거
    unique: list[str] = []
    seen: set[str] = set()
    for name in names:
        if name not in seen:
            seen.add(name)
            unique.append(name)
    return unique


def _parse_display_author_names(raw_author: str | None) -> list[str]:
    if not raw_author:
        return []
    names: list[str] = []
    for part in raw_author.split(","):
        display = re.sub(r"\s*\([^)]*\)", "", part or "").strip()
        if display:
            names.append(display)
    unique: list[str] = []
    seen: set[str] = set()
    for name in names:
        key = _normalize_person_name(name)
        if key and key not in seen:
            seen.add(key)
            unique.append(name)
    return unique


def _normalize_publisher(value: str | None) -> str:
    return re.sub(r"\s+", "", (value or "").strip().lower())


def _safe_year(value: date | datetime | str | None) -> int | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.year
    if isinstance(value, date):
        return value.year
    try:
        return datetime.strptime(str(value)[:10], "%Y-%m-%d").year
    except Exception:
        return None


def _safe_date(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return datetime.strptime(value[:10], "%Y-%m-%d").date()
    except Exception:
        return None


def _safe_pages(value) -> int | None:
    try:
        pages = int(value)
        return pages if pages > 0 else None
    except Exception:
        return None


def _split_categories(category_name: str | None) -> list[str]:
    if not category_name:
        return []
    return [part.strip() for part in category_name.split(">") if part.strip()]


@dataclass
class ExistingBookMeta:
    book: Book
    normalized_title: str
    normalized_authors: set[str]
    normalized_publisher: str
    published_year: int | None
    total_pages: int | None


def _build_existing_book_index(db) -> tuple[dict[str, Book], dict[str, Book], list[ExistingBookMeta]]:
    books = db.query(Book).all()
    isbn13_index: dict[str, Book] = {}
    isbn10_index: dict[str, Book] = {}
    meta_list: list[ExistingBookMeta] = []
    for book in books:
        if book.isbn_13:
            isbn13_index[book.isbn_13] = book
        if book.isbn_10:
            isbn10_index[book.isbn_10] = book
        author_names = {
            _normalize_person_name(link.author.name)
            for link in (book.authors or [])
            if link.author and link.author.name
        }
        meta_list.append(
            ExistingBookMeta(
                book=book,
                normalized_title=_normalize_title(book.title),
                normalized_authors=author_names,
                normalized_publisher=_normalize_publisher(book.publisher),
                published_year=_safe_year(book.published_date),
                total_pages=book.total_pages,
            )
        )
    return isbn13_index, isbn10_index, meta_list


def fetch_item_list(*, query_type: str, max_results: int = MAX_RESULTS_PER_LIST, category_id: int | None = None) -> list[dict]:
    params = {
        "ttbkey": _api_key(),
        "QueryType": query_type,
        "MaxResults": max_results,
        "start": 1,
        "SearchTarget": "Book",
        "output": "js",
        "Version": "20131101",
        "Cover": "Big",
        "OptResult": "authors,subInfo,categoryId",
    }
    if category_id:
        params["CategoryId"] = category_id
    response = requests.get(ALADIN_API_URL, params=params, timeout=20)
    response.raise_for_status()
    return response.json().get("item", []) or []


def fetch_item_lookup(isbn13: str | None, isbn10: str | None) -> dict | None:
    candidates: list[tuple[str, str]] = []
    if isbn13:
        candidates.append(("ISBN13", isbn13))
    if isbn10:
        candidates.append(("ISBN", isbn10))
    for id_type, item_id in candidates:
        params = {
            "ttbkey": _api_key(),
            "itemIdType": id_type,
            "ItemId": item_id,
            "output": "js",
            "Version": "20131101",
            "OptResult": "authors,subInfo",
        }
        response = requests.get(ALADIN_LOOKUP_URL, params=params, timeout=20)
        response.raise_for_status()
        item = (response.json().get("item") or [{}])[0]
        if item:
            return item
    return None


def _is_recent_korean_popular(item: dict) -> bool:
    pub_year = _safe_year(item.get("pubDate"))
    if pub_year not in ALLOWED_YEARS:
        return False
    category_name = item.get("categoryName") or ""
    return category_name.startswith("국내도서>")


def _find_duplicate_book(
    *,
    isbn13_index: dict[str, Book],
    isbn10_index: dict[str, Book],
    existing_meta: list[ExistingBookMeta],
    isbn13: str | None,
    isbn10: str | None,
    title: str,
    author_names: list[str],
    publisher: str | None,
    published_date: date | None,
    total_pages: int | None,
) -> Book | None:
    if isbn13 and isbn13 in isbn13_index:
        return isbn13_index[isbn13]
    if isbn10 and isbn10 in isbn10_index:
        return isbn10_index[isbn10]

    normalized_title = _normalize_title(title)
    normalized_authors = set(author_names)
    normalized_publisher = _normalize_publisher(publisher)
    published_year = _safe_year(published_date)

    for meta in existing_meta:
        if normalized_title != meta.normalized_title:
            continue
        if not normalized_authors or not meta.normalized_authors:
            continue

        exact_authors = normalized_authors == meta.normalized_authors
        overlap_authors = bool(normalized_authors & meta.normalized_authors)
        same_publisher = bool(normalized_publisher and normalized_publisher == meta.normalized_publisher)
        similar_year = (
            published_year is not None
            and meta.published_year is not None
            and abs(published_year - meta.published_year) <= 1
        )
        similar_pages = (
            total_pages is not None
            and meta.total_pages is not None
            and abs(total_pages - meta.total_pages) <= 20
        )

        if exact_authors:
            return meta.book
        if overlap_authors and ((same_publisher and similar_year) or (same_publisher and similar_pages) or (similar_year and similar_pages)):
            return meta.book
    return None


def _get_or_create_author(db, name: str) -> Author:
    normalized = _normalize_person_name(name)
    author = db.query(Author).filter(func.replace(func.lower(Author.name), " ", "") == normalized).first()
    if author:
        return author
    author = Author(name=name)
    db.add(author)
    db.flush()
    return author


def _link_book_authors(db, book: Book, display_authors: Iterable[str]) -> None:
    existing_author_ids = {link.author_id for link in (book.authors or [])}
    for author_name in display_authors:
        author = _get_or_create_author(db, author_name)
        if author.id in existing_author_ids:
            continue
        db.add(BookAuthor(book_id=book.id, author_id=author.id))
        existing_author_ids.add(author.id)


def _link_book_categories(db, book: Book, category_name: str | None) -> None:
    existing = {
        row.category_name
        for row in db.query(BookCategory).filter(BookCategory.book_id == book.id).all()
    }
    for category in _split_categories(category_name):
        if category in existing:
            continue
        db.add(BookCategory(book_id=book.id, category_name=category))
        existing.add(category)



def _upsert_recent_book(db, item: dict, *, isbn13_index, isbn10_index, existing_meta) -> tuple[str, Book | None]:
    isbn13 = item.get("isbn13") or None
    isbn10 = item.get("isbn") or None
    lookup = fetch_item_lookup(isbn13, isbn10) or item
    time.sleep(REQUEST_SLEEP_SECONDS)

    title = lookup.get("title") or item.get("title") or ""
    author_names = _parse_author_names(lookup.get("author") or item.get("author"))
    display_authors = _parse_display_author_names(lookup.get("author") or item.get("author"))
    publisher = lookup.get("publisher") or item.get("publisher")
    published_date = _safe_date(lookup.get("pubDate") or item.get("pubDate"))
    total_pages = _safe_pages((lookup.get("subInfo") or {}).get("itemPage"))
    category_name = lookup.get("categoryName") or item.get("categoryName")
    description = lookup.get("description") or item.get("description")
    cover = lookup.get("cover") or item.get("cover")

    duplicate = _find_duplicate_book(
        isbn13_index=isbn13_index,
        isbn10_index=isbn10_index,
        existing_meta=existing_meta,
        isbn13=isbn13,
        isbn10=isbn10,
        title=title,
        author_names=author_names,
        publisher=publisher,
        published_date=published_date,
        total_pages=total_pages,
    )
    if duplicate:
        # 최신 메타는 보강만 하고 새 책은 만들지 않는다.
        if duplicate.isbn_13 is None and isbn13:
            duplicate.isbn_13 = isbn13
            isbn13_index[isbn13] = duplicate
        if duplicate.isbn_10 is None and isbn10:
            duplicate.isbn_10 = isbn10
            isbn10_index[isbn10] = duplicate
        if not duplicate.total_pages and total_pages:
            duplicate.total_pages = total_pages
        if not duplicate.thumbnail and cover:
            duplicate.thumbnail = cover
            duplicate.small_thumbnail = cover
        if not duplicate.description and description:
            duplicate.description = description
        if not duplicate.publisher and publisher:
            duplicate.publisher = publisher
        if not duplicate.published_date and published_date:
            duplicate.published_date = published_date
        if not duplicate.category and category_name:
            duplicate.category = category_name
        _link_book_authors(db, duplicate, display_authors)
        _link_book_categories(db, duplicate, category_name)
        return "duplicate", duplicate

    book = Book(
        isbn_10=isbn10,
        isbn_13=isbn13,
        title=title,
        publisher=publisher,
        published_date=published_date,
        language="ko",
        category=category_name,
        total_pages=total_pages,
        thumbnail=cover,
        small_thumbnail=cover,
        description=description,
    )
    db.add(book)
    db.flush()
    _link_book_authors(db, book, display_authors)
    _link_book_categories(db, book, category_name)

    if isbn13:
        isbn13_index[isbn13] = book
    if isbn10:
        isbn10_index[isbn10] = book
    existing_meta.append(
        ExistingBookMeta(
            book=book,
            normalized_title=_normalize_title(title),
            normalized_authors=set(author_names),
            normalized_publisher=_normalize_publisher(publisher),
            published_year=_safe_year(published_date),
            total_pages=total_pages,
        )
    )
    return "created", book


def import_recent_popular_books() -> None:
    db = SessionLocal()
    try:
        isbn13_index, isbn10_index, existing_meta = _build_existing_book_index(db)
        sources: list[tuple[str, str, int | None]] = [("bestseller_all", "Bestseller", None)]
        sources.extend((f"bestseller_{genre}", "Bestseller", category_id) for genre, category_id in GENRE_CATEGORY_IDS.items())

        seen_source_isbn: set[tuple[str, str]] = set()
        created = 0
        deduped = 0
        skipped = 0

        for list_type, query_type, category_id in sources:
            items = fetch_item_list(query_type=query_type, max_results=MAX_RESULTS_PER_LIST, category_id=category_id)
            filtered = [item for item in items if _is_recent_korean_popular(item)]
            rank = 1
            for item in filtered:
                isbn13 = item.get("isbn13") or ""
                dedupe_source_key = (list_type, isbn13)
                if isbn13 and dedupe_source_key in seen_source_isbn:
                    continue
                status, book = _upsert_recent_book(
                    db,
                    item,
                    isbn13_index=isbn13_index,
                    isbn10_index=isbn10_index,
                    existing_meta=existing_meta,
                )
                if not book:
                    skipped += 1
                    continue
                if status == "created":
                    created += 1
                else:
                    deduped += 1
                if isbn13:
                    seen_source_isbn.add(dedupe_source_key)
                rank += 1
                db.commit()
                time.sleep(REQUEST_SLEEP_SECONDS)

        print(
            f"done created={created} deduped={deduped} skipped={skipped}"
        )
    finally:
        db.close()


if __name__ == "__main__":
    import_recent_popular_books()
