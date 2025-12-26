from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.auth import get_current_user
from app.database import get_db
from app.models import User, Book, SearchQueryStat, Review, BookCategory
from app.services.recommend_personalized import get_personalized_books
from app.schemas.book import BookResponse
from sqlalchemy import func
from datetime import datetime, timedelta

router = APIRouter(prefix="/recommend", tags=["recommend"]) 

def _to_book_response_with_agg(db: Session, b: Book) -> BookResponse:
    avg, cnt = (
        db.query(func.avg(Review.rating), func.count(Review.id))
        .filter(Review.book_id == b.id, Review.rating != None)
        .one()
    )
    authors = [ba.author.name for ba in b.authors]
    categories = [bc.category_name for bc in db.query(BookCategory).filter(BookCategory.book_id == b.id).all()]
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
        authors=authors,
        categories=categories,
    )


@router.get("/for-you", summary="사용자 맞춤 추천")
def for_you(
    limit: int = 20,
    offset: int = 0,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    limit = max(1, min(50, limit))
    offset = max(0, offset)
    items = get_personalized_books(db, user, limit=limit, offset=offset)

    # 콜드스타트/빈 결과일 때 가벼운 fallback: 트렌딩/신규 믹스
    if not items:
        fallback: list[BookResponse] = []
        # 1) 최근 30일 글로벌 인기 검색어 상위 10개로 책 검색 (제목 매칭)
        thirty_days_ago = datetime.utcnow() - timedelta(days=30)
        popular_queries = (
            db.query(SearchQueryStat.query)
            .filter((SearchQueryStat.last_hit_at == None) | (SearchQueryStat.last_hit_at >= thirty_days_ago))
            .order_by(SearchQueryStat.total_count.desc())
            .limit(10)
            .all()
        )
        qwords = [q for (q,) in popular_queries]
        if qwords:
            # 가장 인기 있는 검색어들로 제목 매칭하여 후보 확보
            for q in qwords:
                q_like = f"%{q}%"
                rows = (
                    db.query(Book)
                    .filter(Book.title.ilike(q_like))
                    .order_by(Book.id.desc())
                    .limit(5)
                    .all()
                )
                for b in rows:
                    if len(fallback) >= limit:
                        break
                    fallback.append(_to_book_response_with_agg(db, b))
                if len(fallback) >= limit:
                    break

        # 2) 부족하면 신규(최근 등록 순)로 채우기
        if len(fallback) < limit:
            remain = limit - len(fallback)
            recent_rows = (
                db.query(Book)
                .order_by(Book.id.desc())
                .limit(remain)
                .all()
            )
            for b in recent_rows:
                fallback.append(_to_book_response_with_agg(db, b))

        items = fallback[:limit]
    else:
        # personalized 결과도 응답 형태 통일
        items = [_to_book_response_with_agg(db, b) for b in items]

    return {"items": items}
