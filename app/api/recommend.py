from datetime import datetime, timedelta
from typing import List

from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.database import get_db
from app.models import (
    Book,
    Review,
    SearchQueryStat,
    BookCategory,
    Author,
    BookAuthor,
    UserTaste,
    UserBook,
    ReadingStatus,
    BookList,
)
from app.schemas.book import BookResponse
from app.schemas.recommend import RecommendResponse, CurationsResponse, CurationItem

router = APIRouter(prefix="/recommend", tags=["recommend"])


# ------------------------
# 내부 헬퍼
# ------------------------
def _to_book_response(db: Session, b: Book) -> BookResponse:
    avg, cnt = (
        db.query(func.avg(Review.rating), func.count(Review.id))
        .filter(Review.book_id == b.id, Review.rating != None)
        .one()
    )
    return BookResponse(
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
        average_rating=float(avg) if avg is not None else None,
        review_count=int(cnt or 0),
        authors=[ba.author.name for ba in b.authors],
        categories=[bc.category_name for bc in db.query(BookCategory)
                    .filter(BookCategory.book_id == b.id).all()],
    )


# ------------------------
# (1) 사용자 장르 기반 베스트셀러
# ------------------------
@router.get("/genre-bestseller", response_model=CurationsResponse,
            summary="유저별 관심 장르 베스트셀러 3개 × limit")
def genre_bestseller(
    user_id: int = Query(..., description="유저 ID"),
    limit: int = Query(20, ge=1, le=50),
    db: Session = Depends(get_db),
):
    # 1) 사용자 관심 장르
    user_taste = db.query(UserTaste).filter(UserTaste.user_id == user_id).first()
    if not user_taste:
        raise HTTPException(status_code=404, detail="User taste not found")

    genre_scores = {}

    # 가중치 +3
    for genre in user_taste.genres:
        genre_scores[genre] = genre_scores.get(genre, 0) + 3

    # 가중치 +2 (유저가 평점 4.0 이상 준 장르)
    review_genres = (
        db.query(BookCategory.category_name)
        .join(Review, Review.book_id == BookCategory.book_id)
        .filter(Review.user_id == user_id, Review.rating >= 4.0)
        .distinct()
        .all()
    )
    for (genre,) in review_genres:
        genre_scores[genre] = genre_scores.get(genre, 0) + 2

    # 가중치 +1 (완독한 책 장르)
    completed_genres = (
        db.query(BookCategory.category_name)
        .join(UserBook, UserBook.book_id == BookCategory.book_id)
        .filter(UserBook.user_id == user_id, UserBook.status == ReadingStatus.COMPLETED)
        .distinct()
        .all()
    )
    for (genre,) in completed_genres:
        genre_scores[genre] = genre_scores.get(genre, 0) + 1

    # 상위 3개 장르
    top_genres = [g for g, _ in sorted(genre_scores.items(), key=lambda x: -x[1])][:3]

    # 부족하면 전체 인기 장르로 채우기
    if len(top_genres) < 3:
        genre_counts = (
            db.query(BookCategory.category_name, func.count(BookCategory.book_id))
            .group_by(BookCategory.category_name)
            .order_by(func.count(BookCategory.book_id).desc())
            .all()
        )
        for genre, _ in genre_counts:
            if genre not in top_genres:
                top_genres.append(genre)
            if len(top_genres) == 3:
                break

    if not top_genres:
        raise HTTPException(status_code=404, detail="No genres found for user")

    results = []

    for genre in top_genres:
        list_type = f"bestseller_{genre}"

        # 최신 날짜 가져오기 (scalar 방식)
        latest_date = (
            db.query(BookList.list_date)
            .filter(BookList.list_type == list_type)
            .order_by(BookList.list_date.desc())
            .limit(1)
            .scalar()
        )
        if not latest_date:
            results.append(CurationItem(title=genre, items=[]))
            continue

        # rank순으로 조회
        booklist = (
            db.query(BookList)
            .filter(BookList.list_type == list_type, BookList.list_date == latest_date)
            .order_by(BookList.rank.asc())
            .limit(limit)
            .all()
        )

        isbns = [b.isbn for b in booklist]
        books = db.query(Book).filter(Book.isbn_10.in_(isbns)).all()
        isbn_to_book = {b.isbn_10: b for b in books}

        # 리뷰 agg를 한 번에 수집
        book_ids = [b.id for b in books]
        review_aggs = (
            db.query(
                Review.book_id,
                func.avg(Review.rating),
                func.count(Review.id)
            )
            .filter(Review.book_id.in_(book_ids), Review.rating != None)
            .group_by(Review.book_id)
            .all()
        )
        review_map = {
            row[0]: (float(row[1]) if row[1] is not None else None, int(row[2]))
            for row in review_aggs
        }

        items = []
        for bl in booklist:
            book = isbn_to_book.get(bl.isbn)
            if not book:
                continue
            avg, cnt = review_map.get(book.id, (None, 0))
            items.append(BookResponse(
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
                average_rating=avg,
                review_count=cnt,
                authors=[ba.author.name for ba in book.authors],
                categories=[bc.category_name for bc in db.query(BookCategory)
                            .filter(BookCategory.book_id == book.id).all()],
            ))
        results.append(CurationItem(title=genre, items=items))

    return CurationsResponse(curations=results)


# ------------------------
# (2) 전체 베스트셀러
# ------------------------
@router.get("/bestseller", response_model=RecommendResponse, summary="전체 베스트셀러 limit권")
def bestseller(limit: int = Query(20, ge=1, le=50),
               db: Session = Depends(get_db)):
    latest_date = (
        db.query(BookList.list_date)
        .filter(BookList.list_type == "bestseller_all")
        .order_by(BookList.list_date.desc())
        .limit(1)
        .scalar()
    )
    if not latest_date:
        return RecommendResponse(items=[])

    booklist = (
        db.query(BookList)
        .filter(BookList.list_type == "bestseller_all", BookList.list_date == latest_date)
        .order_by(BookList.rank.asc())
        .limit(limit)
        .all()
    )

    books = db.query(Book).filter(Book.isbn_10.in_([b.isbn for b in booklist])).all()
    isbn_to_book = {b.isbn_10: b for b in books}

    items = [_to_book_response(db, isbn_to_book[b.isbn])
             for b in booklist if b.isbn in isbn_to_book]
    return RecommendResponse(items=items)


# ------------------------
# (3) 전체 신간
# ------------------------
@router.get("/new", response_model=RecommendResponse, summary="전체 신간 limit권")
def new_books(limit: int = Query(20, ge=1, le=50),
              db: Session = Depends(get_db)):
    latest_date = (
        db.query(BookList.list_date)
        .filter(BookList.list_type == "new_all")
        .order_by(BookList.list_date.desc())
        .limit(1)
        .scalar()
    )
    if not latest_date:
        return RecommendResponse(items=[])

    booklist = (
        db.query(BookList)
        .filter(BookList.list_type == "new_all", BookList.list_date == latest_date)
        .order_by(BookList.rank.asc())
        .limit(limit)
        .all()
    )

    books = db.query(Book).filter(Book.isbn_10.in_([b.isbn for b in booklist])).all()
    isbn_to_book = {b.isbn_10: b for b in books}

    items = [_to_book_response(db, isbn_to_book[b.isbn])
             for b in booklist if b.isbn in isbn_to_book]
    return RecommendResponse(items=items)


# ------------------------
# (4) 인기 추천
# ------------------------
@router.get("/popular", response_model=RecommendResponse,
            summary="최근 리뷰/평점 많은 순")
def popular(
    days: int = Query(30, ge=1, le=365),
    limit: int = Query(20, ge=1, le=50),
    db: Session = Depends(get_db),
):
    since = datetime.utcnow() - timedelta(days=days)

    agg = (
        db.query(
            Review.book_id.label("bid"),
            func.count(Review.id).label("review_count"),
            func.count(func.nullif(Review.rating, None)).label("rating_count"),
            func.avg(Review.rating).label("avg_rating"),
        )
        .filter(Review.created_date >= since.date())
        .group_by(Review.book_id)
        .order_by(
            func.count(Review.id).desc(),
            func.count(func.nullif(Review.rating, None)).desc(),
            func.avg(Review.rating).desc(),
        )
        .limit(limit)
        .all()
    )

    book_ids = [row.bid for row in agg]
    books = db.query(Book).filter(Book.id.in_(book_ids)).all()
    id_to_book = {b.id: b for b in books}

    ordered = [id_to_book[i] for i in book_ids if i in id_to_book]

    return RecommendResponse(items=[_to_book_response(db, b) for b in ordered])


# ------------------------
# (5) 검색 트렌드 기반 추천
# ------------------------
@router.get("/trending-search", response_model=RecommendResponse,
            summary="검색어 히트 기반 추천")
def trending_search(
    days: int = Query(30, ge=1, le=365),
    limit: int = Query(20, ge=1, le=50),
    db: Session = Depends(get_db),
):
    since = datetime.utcnow() - timedelta(days=days)

    top_queries = (
        db.query(SearchQueryStat.query, SearchQueryStat.total_count.label("cnt"))
        .filter(SearchQueryStat.last_hit_at >= since)
        .order_by(SearchQueryStat.total_count.desc())
        .limit(100)
        .all()
    )

    seen_ids = []
    seen_set = set()

    for q, _ in top_queries:
        qlike = f"%{q}%"

        author_book_ids = (
            db.query(BookAuthor.book_id)
            .join(Author, Author.id == BookAuthor.author_id)
            .filter(Author.name.ilike(qlike))
            .subquery()
        )

        cand = (
            db.query(Book.id)
            .filter(
                (Book.id.in_(author_book_ids)) |
                (Book.title.ilike(qlike)) |
                (Book.publisher.ilike(qlike))
            )
            .order_by(Book.id.desc())
            .limit(10)
            .all()
        )

        for (bid,) in cand:
            if bid not in seen_set:
                seen_set.add(bid)
                seen_ids.append(bid)
            if len(seen_ids) >= limit:
                break

        if len(seen_ids) >= limit:
            break

    books = db.query(Book).filter(Book.id.in_(seen_ids)).all()
    id_to_book = {b.id: b for b in books}
    ordered = [id_to_book[i] for i in seen_ids if i in id_to_book]

    return RecommendResponse(items=[_to_book_response(db, b) for b in ordered])


# ------------------------
# (6) 코멘트 기반 큐레이션 목록
# ------------------------
_CURATION_THEMES = [
    "한 해를 마무리하며 읽기 좋은 책",
    "동기부여가 필요할 때",
    "경제・투자 공부를 시작하는 사람에게",
    "한 번 잡으면 멈출 수 없는 미스터리 & 스릴러",
    "짧아서 더 좋은 책 (에세이/단편)",
    "SF 세계로 입문하는 사람에게",
]


@router.get("/curations", response_model=CurationsResponse,
            summary="테마별 큐레이션 limit권 × themes")
def curations(limit: int = Query(15, ge=1, le=50),
              db: Session = Depends(get_db)):
    results: List[CurationItem] = []

    for theme in _CURATION_THEMES:
        list_type = f"comment_{theme}"

        latest_date = (
            db.query(BookList.list_date)
            .filter(BookList.list_type == list_type)
            .order_by(BookList.list_date.desc())
            .limit(1)
            .scalar()
        )
        if not latest_date:
            results.append(CurationItem(title=theme, items=[]))
            continue

        booklist = (
            db.query(BookList)
            .filter(BookList.list_type == list_type, BookList.list_date == latest_date)
            .order_by(BookList.rank.asc())
            .limit(limit)
            .all()
        )

        books = db.query(Book).filter(Book.isbn_10.in_([b.isbn for b in booklist])).all()
        isbn_to_book = {b.isbn_10: b for b in books}

        items = [_to_book_response(db, isbn_to_book[b.isbn])
             for b in booklist if b.isbn in isbn_to_book]

        results.append(CurationItem(title=theme, items=items))

    return CurationsResponse(curations=results)


# ------------------------
# (7) 단일 큐레이션 테마
# ------------------------
@router.get("/curations/{theme}", response_model=RecommendResponse,
            summary="단일 테마 큐레이션")
def curations_by_theme(
    theme: str,
    limit: int = Query(15, ge=1, le=50),
    db: Session = Depends(get_db),
):
    list_type = f"comment_{theme}"

    latest_date = (
        db.query(BookList.list_date)
        .filter(BookList.list_type == list_type)
        .order_by(BookList.list_date.desc())
        .limit(1)
        .scalar()
    )
    if not latest_date:
        return RecommendResponse(items=[])

    booklist = (
        db.query(BookList)
        .filter(BookList.list_type == list_type, BookList.list_date == latest_date)
        .order_by(BookList.rank.asc())
        .limit(limit)
        .all()
    )

    books = db.query(Book).filter(Book.isbn_10.in_([b.isbn for b in booklist])).all()
    isbn_to_book = {b.isbn_10: b for b in books}

    items = [_to_book_response(db, isbn_to_book[b.isbn])
             for b in booklist if b.isbn in isbn_to_book]

    return RecommendResponse(items=items)
