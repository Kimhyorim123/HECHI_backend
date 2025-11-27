import re

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import func
from datetime import date

from typing import Optional
from app.core.auth import get_current_user
from app.database import get_db
from app.models import Book, Author, BookAuthor, Review, User
from app.schemas.book import (
    BookCreateRequest,
    BookResponse,
    BookDetailResponse,
    BookSearchResponse,
)

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
    # 중복 ISBN은 막기(있으면 반환)
    if payload.isbn:
        existing = db.query(Book).filter(Book.isbn == payload.isbn).first()
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
        isbn=payload.isbn,
        title=payload.title,
        publisher=payload.publisher,
        published_date=pd,
        language=payload.language,
        category=_normalize_category(payload.category) if payload.category else None,
        total_pages=payload.total_pages,
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
    return book


@router.get("/{book_id}", response_model=BookDetailResponse)
def get_book_detail(book_id: int, db: Session = Depends(get_db)):
    book = db.query(Book).filter(Book.id == book_id).first()
    if not book:
        raise HTTPException(status_code=404, detail="책을 찾을 수 없습니다")

    author_names = [ba.author.name for ba in book.authors]
    avg, cnt = db.query(func.avg(Review.rating), func.count(Review.id)).filter(Review.book_id == book_id).one()

    return BookDetailResponse(
        id=book.id,
        isbn=book.isbn,
        title=book.title,
        publisher=book.publisher,
        published_date=book.published_date.isoformat() if book.published_date else None,
        language=book.language,
        category=book.category,
        total_pages=book.total_pages,
        authors=author_names,
        average_rating=float(avg) if avg is not None else None,
        review_count=cnt,
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
        .filter((Book.id.in_(author_book_ids.select())) | (Book.title.ilike(q_like)) | (Book.publisher.ilike(q_like)))
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
                isbn=b.isbn,
                title=b.title,
                publisher=b.publisher,
                published_date=b.published_date.isoformat() if b.published_date else None,
                language=b.language,
                category=b.category,
                total_pages=b.total_pages,
            )
        )
    return BookSearchResponse(items=normalized)
