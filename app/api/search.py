from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import func
from datetime import datetime
import re

from app.core.auth import get_current_user
from app.database import get_db
from app.models import (
    User,
    Book,
    Author,
    BookAuthor,
    BookCategory,
    SearchHistory,
    SearchQueryStat,
    UserBook,
    ReadingStatus,
)
from app.schemas.search import (
    SearchRequest,
    SearchResult,
    AuthorItem,
    SearchHistoryItem,
    BarcodeSearchResponse,
)
from app.schemas.book import BookResponse
from app.services.google_books import get_client, map_volume_to_book_fields


router = APIRouter(prefix="/search", tags=["search"])


def _normalize_isbn(s: str) -> str:
    return re.sub(r"[^0-9Xx]", "", s).upper()


@router.post("/query", response_model=SearchResult, summary="텍스트로 검색(책/작가) + 기록 저장")
def search_query(
    payload: SearchRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    q = payload.query.strip()
    if not q:
        raise HTTPException(status_code=400, detail="query가 비어 있습니다")

    if payload.save_history:
        # 개인 검색 기록 저장
        h = SearchHistory(user_id=current_user.id, query=q, created_at=datetime.utcnow())
        db.add(h)
        # 전역 검색어 통계 업데이트
        stat = db.query(SearchQueryStat).filter(SearchQueryStat.query == q).first()
        if not stat:
            stat = SearchQueryStat(query=q, total_count=1, last_hit_at=datetime.utcnow())
            db.add(stat)
        else:
            stat.total_count += 1
            stat.last_hit_at = datetime.utcnow()
        db.flush()
        db.commit()

    q_like = f"%{q}%"

    # 책 검색: 제목/출판사 또는 저자명 매칭
    author_book_ids = (
        db.query(BookAuthor.book_id)
        .join(Author, Author.id == BookAuthor.author_id)
        .filter(Author.name.ilike(q_like))
        .subquery()
    )
    # 책 검색: 제목 또는 저자명 매칭(출판사 매칭 제외)
    books = (
        db.query(Book)
        .filter((Book.id.in_(author_book_ids.select())) | (Book.title.ilike(q_like)))
        .order_by(Book.id.desc())
        .limit(payload.limit)
        .all()
    )
    book_items = []
    for b in books:
        authors = [ba.author.name for ba in b.authors]
        categories = [bc.category_name for bc in db.query(BookCategory).filter(BookCategory.book_id == b.id).all()]
        book_items.append(
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
                authors=authors,
                categories=categories,
            )
        )

    # 작가 검색
    authors = db.query(Author).filter(Author.name.ilike(q_like)).order_by(Author.id.desc()).limit(10).all()
    author_items = [AuthorItem(id=a.id, name=a.name) for a in authors]

    return SearchResult(books=book_items, authors=author_items)


@router.get("/history", response_model=list[SearchHistoryItem], summary="개인별 최근 검색어 목록")
def search_history(
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    rows = (
        db.query(SearchHistory)
        .filter(SearchHistory.user_id == current_user.id)
        .order_by(SearchHistory.id.desc())
        .limit(limit)
        .all()
    )
    return [SearchHistoryItem(id=r.id, query=r.query, created_at=r.created_at.isoformat()) for r in rows]


@router.delete("/history", summary="개인별 검색 기록 전체 삭제")
def clear_history(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    db.query(SearchHistory).filter(SearchHistory.user_id == current_user.id).delete()
    db.commit()
    return {"ok": True}


@router.delete("/history/{history_id}", summary="개인별 검색 기록 단건 삭제")
def delete_history_item(
    history_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    row = (
        db.query(SearchHistory)
        .filter(SearchHistory.user_id == current_user.id, SearchHistory.id == history_id)
        .first()
    )
    if not row:
        raise HTTPException(status_code=404, detail="기록을 찾을 수 없습니다")
    db.delete(row)
    db.commit()
    return {"ok": True}


@router.get("/barcode", response_model=BarcodeSearchResponse, summary="바코드(ISBN)로 검색")
def search_barcode(
    isbn: str = Query(..., description="ISBN-10/13, 하이픈 허용"),
    auto_import: bool = Query(True, description="DB에 없으면 Google에서 가져와 저장"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    code = _normalize_isbn(isbn)
    if len(code) not in (10, 13):
        raise HTTPException(status_code=400, detail="ISBN은 10자리 또는 13자리여야 합니다")

    book = db.query(Book).filter((Book.isbn_10 == code) | (Book.isbn_13 == code)).first()
    if not book and auto_import:
        client = get_client()
        vols = client.by_isbn(code)
        if vols:
            fields = map_volume_to_book_fields(vols[0])
            # 최소 title 필요
            if fields.get("title"):
                book = Book(
                    isbn=fields.get("isbn") or code,
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
                for cname in fields.get("categories", []) or []:
                    db.add(BookCategory(book_id=book.id, category_name=cname))
                for name in fields.get("authors", []) or []:
                    name = name.strip()
                    if not name:
                        continue
                    a = db.query(Author).filter(func.lower(Author.name) == name.lower()).first()
                    if not a:
                        a = Author(name=name)
                        db.add(a)
                        db.flush()
                    db.add(BookAuthor(book_id=book.id, author_id=a.id))
                db.commit()

    if not book:
        return BarcodeSearchResponse(book=None, already_registered=False)

    already = db.query(UserBook).filter(UserBook.user_id == current_user.id, UserBook.book_id == book.id).first() is not None
    authors = [ba.author.name for ba in book.authors]
    categories = [bc.category_name for bc in db.query(BookCategory).filter(BookCategory.book_id == book.id).all()]
    return BarcodeSearchResponse(
        already_registered=already,
        book=BookResponse(
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
            authors=authors,
            categories=categories,
        ),
    )


@router.post("/register-reading", summary="검색 결과/바코드 팝업에서 '예' 선택 시 읽는 중 등록")
def register_reading(
    book_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    ub = db.query(UserBook).filter(UserBook.user_id == current_user.id, UserBook.book_id == book_id).first()
    if not ub:
        ub = UserBook(user_id=current_user.id, book_id=book_id)
        db.add(ub)
        db.flush()
    ub.status = ReadingStatus.READING
    db.commit()
    return {"ok": True, "user_book_id": ub.id}
