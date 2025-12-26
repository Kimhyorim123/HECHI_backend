import re

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import func
from datetime import date

from typing import Optional, List
from app.core.auth import get_current_user
from app.database import get_db
from app.models import Book, Author, BookAuthor, Review, User, BookCategory
from app.schemas.book import (
    BookCreateRequest,
    BookResponse,
    BookDetailResponse,
    BookSearchResponse,
    GoogleImportRequest,
    GoogleImportResult,
    GoogleQueryImportRequest,
)
from app.services.google_books import get_client, map_volume_to_book_fields

router = APIRouter(prefix="/books", tags=["books"])


_CATEGORY_MAP = {
    r"romance": "로맨스",
    r"horror": "공포",
    r"contemporary": "현대문학",
    r"fantasy": "판타지",
    r"science fiction|sci[- ]?fi|sf": "SF",
    r"mystery|thriller": "미스터리",
    r"history|historical": "역사",
}


def _normalize_category(raw: Optional[str]) -> Optional[str]:
    if not raw:
        return None
    s = raw.lower()
    for pattern, label in _CATEGORY_MAP.items():
        if re.search(pattern, s):
            return label
    # 기본은 raw의 마지막 토큰 반환
    parts = [p.strip() for p in raw.split("/") if p.strip()]
    return parts[-1] if parts else raw


@router.post("/", response_model=BookResponse)
def create_book(
    payload: BookCreateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),  # 인증된 사용자만 등록 가능(운영툴 대용)
):
    # ISBN 정규화: 하이픈/공백 제거, 대문자 X 허용
    if payload.isbn:
        normalized_isbn = re.sub(r"[^0-9Xx]", "", payload.isbn)
        # ISBN-13 정책인 경우 길이 검증(옵션)
        if len(normalized_isbn) not in (10, 13):
            raise HTTPException(status_code=400, detail="ISBN은 10자리 또는 13자리여야 합니다")
        payload.isbn = normalized_isbn.upper()
    # 중복 ISBN은 막기(있으면 반환)
    if payload.isbn:
        existing = db.query(Book).filter(Book.isbn_10 == payload.isbn).first()
        if existing:
            return existing

    # published_date 문자열(YYYY-MM-DD)을 Date로 파싱
    pd = None
    if payload.published_date:
        try:
            pd = date.fromisoformat(payload.published_date)
        except ValueError:
            raise HTTPException(status_code=400, detail="published_date 형식은 YYYY-MM-DD 입니다")

    book = Book(
        isbn_10=payload.isbn,
        title=payload.title,
        publisher=payload.publisher,
        published_date=pd,
        language=payload.language,
        category=_normalize_category(payload.category) if payload.category else None,
        total_pages=payload.total_pages,
        thumbnail=payload.thumbnail,
        small_thumbnail=payload.small_thumbnail,
        google_rating=payload.google_rating,
        google_ratings_count=payload.google_ratings_count,
        description=payload.description,
    )
    db.add(book)
    db.flush()

    # 저자 처리
    for name in payload.authors or []:
        name = name.strip()
        if not name:
            continue
        author = db.query(Author).filter(func.lower(Author.name) == name.lower()).first()
        if not author:
            author = Author(name=name)
            db.add(author)
            db.flush()
        link = BookAuthor(book_id=book.id, author_id=author.id)
        db.add(link)

    db.commit()
    db.refresh(book)
    return BookResponse(
        id=book.id,
        isbn=book.isbn_10,
        title=book.title,
        publisher=book.publisher,
        published_date=book.published_date.isoformat() if book.published_date else None,
        language=book.language,
        category=book.category,
        total_pages=book.total_pages,
        thumbnail=getattr(book, "thumbnail", None),
        small_thumbnail=getattr(book, "small_thumbnail", None),
        google_rating=getattr(book, "google_rating", None),
        google_ratings_count=getattr(book, "google_ratings_count", None),
        description=getattr(book, "description", None),
    )


@router.get("/{book_id}", response_model=BookDetailResponse)
def get_book_detail(book_id: int, db: Session = Depends(get_db)):
    book = db.query(Book).filter(Book.id == book_id).first()
    if not book:
        raise HTTPException(status_code=404, detail="책을 찾을 수 없습니다")

    author_names = [ba.author.name for ba in book.authors]
    avg, cnt = db.query(func.avg(Review.rating), func.count(Review.id)).filter(Review.book_id == book_id).one()
    # Build 0~5 by 0.5 histogram
    ratings = db.query(Review.rating).filter(Review.book_id == book_id).all()
    bins = [x / 2 for x in range(0, 11)]  # 0.0, 0.5, ..., 5.0
    hist = {f"{b:.1f}": 0 for b in bins}
    for (r,) in ratings:
        if r is None:
            continue
        # round to nearest 0.5 step to avoid float artifacts
        b = round(r * 2) / 2
        key = f"{b:.1f}"
        if key in hist:
            hist[key] += 1

    return BookDetailResponse(
        id=book.id,
        isbn=book.isbn_10,
        title=book.title,
        publisher=book.publisher,
        published_date=book.published_date.isoformat() if book.published_date else None,
        language=book.language,
        category=book.category,
        total_pages=book.total_pages,
        authors=author_names,
        average_rating=float(avg) if avg is not None else None,
        review_count=cnt,
        rating_histogram=hist,
        thumbnail=getattr(book, "thumbnail", None),
        small_thumbnail=getattr(book, "small_thumbnail", None),
        google_rating=getattr(book, "google_rating", None),
        google_ratings_count=getattr(book, "google_ratings_count", None),
        description=getattr(book, "description", None),
    )


@router.get("/", response_model=BookSearchResponse)
def search_books(
    q: str = Query("", description="제목/저자/출판사 부분검색"),
    limit: int = 20,
    db: Session = Depends(get_db),
):
    q_like = f"%{q}%"

    # 제목/출판사 매칭
    # 제목/출판사 매칭 (중간 단계 변수 제거)

    # 저자 이름 매칭해서 책 id 모으기
    author_book_ids = (
        db.query(BookAuthor.book_id)
        .join(Author, Author.id == BookAuthor.author_id)
        .filter(Author.name.ilike(q_like))
        .subquery()
    )

    items = (
        db.query(Book)
        .filter(
            (Book.id.in_(author_book_ids.select())) |
            (Book.title.ilike(q_like)) |
            (Book.publisher.ilike(q_like)) |
            (Book.isbn_10 == q) |
            (Book.isbn_13 == q)
        )
        .order_by(Book.id.desc())
        .limit(limit)
        .all()
    )
    # 응답 변환: published_date를 문자열로 표준화
    normalized = []
    for b in items:
        normalized.append(
            BookResponse(
                id=b.id,
                isbn=b.isbn_10,
                title=b.title,
                publisher=b.publisher,
                published_date=b.published_date.isoformat() if b.published_date else None,
                language=b.language,
                category=b.category,
                total_pages=b.total_pages,
                thumbnail=getattr(b, "thumbnail", None),
                small_thumbnail=getattr(b, "small_thumbnail", None),
                google_rating=getattr(b, "google_rating", None),
                google_ratings_count=getattr(b, "google_ratings_count", None),
            )
        )
        fields = map_volume_to_book_fields(v)
        isbn = fields.get("isbn")
        if not fields.get("title"):
            continue
        existing = None
        if isbn:
            existing = db.query(Book).filter(Book.isbn == isbn).first()
        if existing:
            # 업데이트 가능한 외부 필드만 수정
            existing.thumbnail = fields.get("thumbnail") or existing.thumbnail
            existing.small_thumbnail = fields.get("small_thumbnail") or existing.small_thumbnail
            existing.google_rating = fields.get("google_rating") or existing.google_rating
            existing.google_ratings_count = fields.get("google_ratings_count") or existing.google_ratings_count
            # 카테고리 갱신: 중복 방지 후 추가
            for cname in fields.get("categories", []):
                if not cname:
                    continue
                exists_cat = db.query(BookCategory).filter(BookCategory.book_id == existing.id, BookCategory.category_name == cname).first()
                if not exists_cat:
                    db.add(BookCategory(book_id=existing.id, category_name=cname))
            db.flush()
            author_names = [ba.author.name for ba in existing.authors if getattr(ba.author, "name", None)]
            categories = [bc.category_name for bc in db.query(BookCategory).filter(BookCategory.book_id == existing.id).all()]
            updated.append(
                BookResponse(
                    id=existing.id,
                    isbn=existing.isbn,
                    title=existing.title,
                    publisher=existing.publisher,
                    published_date=existing.published_date.isoformat() if existing.published_date else None,
                    language=existing.language,
                    category=existing.category,
                    total_pages=existing.total_pages,
                    thumbnail=getattr(existing, "thumbnail", None),
                    small_thumbnail=getattr(existing, "small_thumbnail", None),
                    google_rating=getattr(existing, "google_rating", None),
                    google_ratings_count=getattr(existing, "google_ratings_count", None),
                    authors=author_names,
                    categories=categories,
                )
            )
            skipped.append(isbn)
            continue
        book = Book(
            isbn=isbn,
            title=fields.get("title"),
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
        for cname in fields.get("categories", []):
            if cname:
                db.add(BookCategory(book_id=book.id, category_name=cname))
        for name in fields.get("authors", []):
            name = name.strip()
            if not name:
                continue
            author = db.query(Author).filter(func.lower(Author.name) == name.lower()).first()
            if not author:
                author = Author(name=name)
                db.add(author)
                db.flush()
            link = BookAuthor(book_id=book.id, author_id=author.id)
            db.add(link)
        created.append(
            BookResponse(
                id=book.id,
                isbn=book.isbn_10,
                title=book.title,
                publisher=book.publisher,
                published_date=book.published_date.isoformat() if book.published_date else None,
                language=book.language,
                category=book.category,
                total_pages=book.total_pages,
                thumbnail=getattr(book, "thumbnail", None),
                small_thumbnail=getattr(book, "small_thumbnail", None),
                google_rating=getattr(book, "google_rating", None),
                google_ratings_count=getattr(book, "google_ratings_count", None),
                authors=[a.name for a in db.query(Author).join(BookAuthor, BookAuthor.author_id == Author.id).filter(BookAuthor.book_id == book.id).all()],
                categories=[bc.category_name for bc in db.query(BookCategory).filter(BookCategory.book_id == book.id).all()],
            )
        )
    db.commit()
    return GoogleImportResult(created=created, skipped=skipped, updated=updated)


@router.post("/import/google/query", response_model=GoogleImportResult, tags=["books"])
def import_from_google_query(
    payload: GoogleQueryImportRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    client = get_client()
    created: List[BookResponse] = []
    updated: List[BookResponse] = []
    skipped: List[str] = []
    total_created = 0
    for page in range(payload.pages):
        start_index = payload.start_index + page * payload.page_size
        volumes = client.by_query_paged(payload.query, start_index=start_index, max_results=payload.page_size)
        if not volumes:
            break
        for v in volumes:
            fields = map_volume_to_book_fields(v)
            isbn = fields.get("isbn")
            if payload.exclude_no_isbn and not isbn:
                continue
            if payload.language and fields.get("language") != payload.language:
                continue
            if not fields.get("title"):
                continue
            existing = None
            if isbn:
                existing = db.query(Book).filter(Book.isbn == isbn).first()
            if existing:
                existing.thumbnail = fields.get("thumbnail") or existing.thumbnail
                existing.small_thumbnail = fields.get("small_thumbnail") or existing.small_thumbnail
                existing.google_rating = fields.get("google_rating") or existing.google_rating
                existing.google_ratings_count = fields.get("google_ratings_count") or existing.google_ratings_count
                for cname in fields.get("categories", []):
                    if not cname:
                        continue
                    exists_cat = db.query(BookCategory).filter(BookCategory.book_id == existing.id, BookCategory.category_name == cname).first()
                    if not exists_cat:
                        db.add(BookCategory(book_id=existing.id, category_name=cname))
                db.flush()
                updated.append(
                    BookResponse(
                        id=existing.id,
                        isbn=existing.isbn,
                        title=existing.title,
                        publisher=existing.publisher,
                        published_date=existing.published_date.isoformat() if existing.published_date else None,
                        language=existing.language,
                        category=existing.category,
                        total_pages=existing.total_pages,
                        thumbnail=getattr(existing, "thumbnail", None),
                        small_thumbnail=getattr(existing, "small_thumbnail", None),
                        google_rating=getattr(existing, "google_rating", None),
                        google_ratings_count=getattr(existing, "google_ratings_count", None),
                    )
                )
                if isbn:
                    skipped.append(isbn)
                continue
            book = Book(
                isbn=isbn,
                title=fields.get("title"),
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
            for name in fields.get("authors", []):
                name = name.strip()
                if not name:
                    continue
                author = db.query(Author).filter(func.lower(Author.name) == name.lower()).first()
                if not author:
                    author = Author(name=name)
                    db.add(author)
                    db.flush()
                link = BookAuthor(book_id=book.id, author_id=author.id)
                db.add(link)
            created.append(
                BookResponse(
                    id=book.id,
                    isbn=book.isbn,
                    title=book.title,
                    publisher=book.publisher,
                    published_date=book.published_date.isoformat() if book.published_date else None,
                    language=book.language,
                    category=book.category,
                    total_pages=book.total_pages,
                    thumbnail=getattr(book, "thumbnail", None),
                    small_thumbnail=getattr(book, "small_thumbnail", None),
                    google_rating=getattr(book, "google_rating", None),
                    google_ratings_count=getattr(book, "google_ratings_count", None),
                    authors=[a.name for a in db.query(Author).join(BookAuthor, BookAuthor.author_id == Author.id).filter(BookAuthor.book_id == book.id).all()],
                    categories=[bc.category_name for bc in db.query(BookCategory).filter(BookCategory.book_id == book.id).all()],
                )
            )
            total_created += 1
            if payload.max_create and total_created >= payload.max_create:
                db.commit()
                return GoogleImportResult(created=created, skipped=skipped, updated=updated)
    db.commit()
    return GoogleImportResult(created=created, skipped=skipped, updated=updated)
