import datetime
from datetime import date
from app.core.utils import to_seoul
from typing import List, Optional

from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import func, and_, or_, select

from app.core.auth import get_current_user
from app.database import get_db
from app.models import (
    User,
    Book,
    UserBook,
    Review,
    Wishlist,
    BookCategory,
    UserPage,
    ReadingStatus,
)
from app.schemas.book import BookResponse
from app.schemas.library import BookLibraryItem, LibraryResponse

router = APIRouter(prefix="/library", tags=["library"])


def _apply_auto_complete(db: Session, user_id: int):
    """
    READING 상태에서 진행률 >=99%인 책을 COMPLETED로 자동 전환.
    진행률 계산: max(UserPage.end_page) / Book.total_pages * 100.
    """
    # 후보 조회 (total_pages 있을 것, 페이지 기록 존재)
    rows = (
        db.query(
            UserBook.id.label("ub_id"),
            Book.id.label("book_id"),
            Book.total_pages.label("total_pages"),
            func.max(UserPage.end_page).label("max_end"),
        )
        .join(Book, Book.id == UserBook.book_id)
        .outerjoin(UserPage, UserPage.user_book_id == UserBook.id)
        .filter(
            UserBook.user_id == user_id,
            UserBook.status == ReadingStatus.READING,
            Book.total_pages != None,
        )
        .group_by(UserBook.id, Book.id, Book.total_pages)
        .having(func.max(UserPage.end_page) != None)
        .all()
    )
    changed = False
    for r in rows:
        if r.total_pages and r.max_end and r.max_end / r.total_pages >= 0.99:
            ub = db.query(UserBook).filter(UserBook.id == r.ub_id).first()
            if ub and ub.status == ReadingStatus.READING:
                ub.status = ReadingStatus.COMPLETED
                ub.finished_date = date.today()
                changed = True
    if changed:
        db.commit()


def _get_current_page(db: Session, user_id: int, book_id: int) -> Optional[int]:
    # 최근 이벤트 기반 페이지 우선
    from app.models import ReadingSession, ReadingEvent
    last_event_page = (
        db.query(ReadingEvent.page)
        .join(ReadingSession, ReadingEvent.session_id == ReadingSession.id)
        .filter(
            ReadingSession.user_id == user_id,
            ReadingSession.book_id == book_id,
            ReadingEvent.page.isnot(None),
        )
        .order_by(ReadingEvent.occurred_at.desc(), ReadingEvent.id.desc())
        .limit(1)
        .scalar()
    )
    if last_event_page is not None:
        return int(last_event_page)

    # 최근 세션 종료 페이지
    last_session_end = (
        db.query(ReadingSession.end_page)
        .filter(ReadingSession.user_id == user_id, ReadingSession.book_id == book_id)
        .order_by(ReadingSession.id.desc())
        .limit(1)
        .scalar()
    )
    if last_session_end is not None:
        return int(last_session_end)

    # 없으면 UserPage의 max(end_page)
    max_userpage = (
        db.query(func.max(UserPage.end_page))
        .join(UserBook, UserBook.id == UserPage.user_book_id)
        .filter(UserBook.user_id == user_id, UserBook.book_id == book_id)
        .scalar()
    )
    return int(max_userpage) if max_userpage is not None else None


import logging

@router.get("/", response_model=LibraryResponse, summary="도서 보관함 조회")
def get_library(
    shelf: str = Query("reading", description="reading|completed|rated|wishlist"),
    sort: str = Query("latest", description="latest|myRating|avgRating|title"),
    my_rating_in: Optional[str] = Query(None, description="예: 5.0,4.5,4.0"),
    avg_rating_min: Optional[float] = Query(None),
    avg_rating_max: Optional[float] = Query(None),
    year_bucket: Optional[str] = Query(None, description="2020+|2010s|2000s|1990s|1980s|1970s|pre1970"),
    # 언어 필터 제외 요청에 따라 제거
    categories_in: Optional[str] = Query(None, description="카테고리 다중 선택: SF,판타지"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    try:
        # 자동 완독 처리 (reading/ completed 관련 상태일 때만 수행)
        if shelf in ("reading", "completed"):
            _apply_auto_complete(db, current_user.id)

        # 기본 쿼리 구성을 위해 필요한 서브쿼리들
        # 평균 별점 / 리뷰 수
        review_agg_subq = (
            db.query(
                Review.book_id.label("r_book_id"),
                func.avg(Review.rating).label("avg_rating"),
                func.count(Review.id).label("review_count"),
            )
            .group_by(Review.book_id)
            .subquery()
        )
        # 내 별점
        my_rating_subq = (
            db.query(Review.book_id.label("mr_book_id"), Review.rating.label("my_rating"))
            .filter(Review.user_id == current_user.id)
            .subquery()
        )

        # 카테고리 필터 값 파싱
        category_list: List[str] = []
        if categories_in:
            category_list = [c.strip() for c in categories_in.split(",") if c.strip()]

        # my_rating_in 파싱
        my_rating_values: List[float] = []
        if my_rating_in:
            for part in my_rating_in.split(","):
                part = part.strip()
                if not part:
                    continue
                try:
                    my_rating_values.append(float(part))
                except ValueError:
                    raise HTTPException(status_code=400, detail=f"잘못된 my_rating 값: {part}")

        # 연도 필터 조건 구성
        year_conditions = []
        if year_bucket:
            if year_bucket == "2020+":
                year_conditions.append(func.year(Book.published_date) >= 2020)
            elif year_bucket == "2010s":
                year_conditions.append(func.year(Book.published_date).between(2010, 2019))
            elif year_bucket == "2000s":
                year_conditions.append(func.year(Book.published_date).between(2000, 2009))
            elif year_bucket == "1990s":
                year_conditions.append(func.year(Book.published_date).between(1990, 1999))
            elif year_bucket == "1980s":
                year_conditions.append(func.year(Book.published_date).between(1980, 1989))
            elif year_bucket == "1970s":
                year_conditions.append(func.year(Book.published_date).between(1970, 1979))
            elif year_bucket == "pre1970":
                year_conditions.append(func.year(Book.published_date) < 1970)
            else:
                raise HTTPException(status_code=400, detail="year_bucket 값 오류")

        # rated shelf에서는 Review.created_date를 안전하게 사용하기 위해 Review를 join/select에 포함
        if shelf == "rated":
            base_query = db.query(
                Book,
                UserBook.status.label("ub_status"),
                UserBook.created_at.label("added_at"),
                UserBook.started_at.label("started_at"),
                UserBook.completed_at.label("completed_at"),
                review_agg_subq.c.avg_rating,
                review_agg_subq.c.review_count,
                my_rating_subq.c.my_rating,
                Review.created_date.label("review_created_date"),
            ).outerjoin(UserBook, and_(UserBook.book_id == Book.id, UserBook.user_id == current_user.id)) \
                .outerjoin(review_agg_subq, review_agg_subq.c.r_book_id == Book.id) \
                .outerjoin(my_rating_subq, my_rating_subq.c.mr_book_id == Book.id) \
                .outerjoin(Review, and_(Review.book_id == Book.id, Review.user_id == current_user.id))
        else:
            base_query = db.query(
                Book,
                UserBook.status.label("ub_status"),
                UserBook.created_at.label("added_at"),
                UserBook.started_at.label("started_at"),
                UserBook.completed_at.label("completed_at"),
                review_agg_subq.c.avg_rating,
                review_agg_subq.c.review_count,
                my_rating_subq.c.my_rating,
            ).outerjoin(UserBook, and_(UserBook.book_id == Book.id, UserBook.user_id == current_user.id)) \
                .outerjoin(review_agg_subq, review_agg_subq.c.r_book_id == Book.id) \
                .outerjoin(my_rating_subq, my_rating_subq.c.mr_book_id == Book.id)

        # 선반(shelf)에 따른 제한
        if shelf == "reading":
            base_query = base_query.filter(UserBook.status == ReadingStatus.READING)
        elif shelf == "completed":
            base_query = base_query.filter(UserBook.status == ReadingStatus.COMPLETED)
        elif shelf == "rated":
            base_query = base_query.filter(my_rating_subq.c.my_rating != None)
        elif shelf == "wishlist":
            wishlist_subq = (
                db.query(
                    Wishlist.book_id.label("w_book_id"),
                    Wishlist.created_at.label("w_added"),
                    Wishlist.wishlist_at.label("wishlist_at"),
                )
                .filter(Wishlist.user_id == current_user.id)
                .subquery()
            )
            base_query = db.query(
                Book,
                func.coalesce(UserBook.status, "WISHLIST").label("ub_status"),
                wishlist_subq.c.w_added.label("added_at"),
                UserBook.started_at.label("started_at"),
                UserBook.completed_at.label("completed_at"),
                wishlist_subq.c.wishlist_at.label("wishlist_at"),
                review_agg_subq.c.avg_rating,
                review_agg_subq.c.review_count,
                my_rating_subq.c.my_rating,
            ).join(wishlist_subq, wishlist_subq.c.w_book_id == Book.id) \
                .outerjoin(UserBook, and_(UserBook.book_id == Book.id, UserBook.user_id == current_user.id)) \
                .outerjoin(review_agg_subq, review_agg_subq.c.r_book_id == Book.id) \
                .outerjoin(my_rating_subq, my_rating_subq.c.mr_book_id == Book.id)
            # 반드시 wishlist_subq.c.wishlist_at, wishlist_subq.c.w_added만 ORDER BY에 사용
        else:
            raise HTTPException(status_code=400, detail="잘못된 shelf 값")

        # 필터들 적용
        if my_rating_values:
            base_query = base_query.filter(my_rating_subq.c.my_rating.in_(my_rating_values))
        if avg_rating_min is not None:
            base_query = base_query.filter(review_agg_subq.c.avg_rating >= avg_rating_min)
        if avg_rating_max is not None:
            base_query = base_query.filter(review_agg_subq.c.avg_rating <= avg_rating_max)
        # ...이하 기존 코드 유지...
    except Exception as e:
        logging.exception("도서 보관함 API 예외 발생")
        raise
        base_query = base_query.filter(review_agg_subq.c.avg_rating <= avg_rating_max)
    if year_conditions:
        for cond in year_conditions:
            base_query = base_query.filter(cond)
    if category_list:
        cat_subq = (
            db.query(BookCategory.book_id)
            .filter(BookCategory.category_name.in_(category_list))
            .subquery()
        )
        base_query = base_query.filter(Book.id.in_(select(cat_subq)))

    # 정렬
    if sort == "latest":
        if shelf == "reading":
            base_query = base_query.order_by(UserBook.started_at.is_(None), UserBook.started_at.desc())
        elif shelf == "completed":
            base_query = base_query.order_by(UserBook.completed_at.is_(None), UserBook.completed_at.desc())
        elif shelf == "rated":
            # 최근 별점 작성일 기준 정렬(Review.created_date가 select에 포함되어야 함)
            base_query = base_query.order_by(Review.created_date.is_(None), Review.created_date.desc())
        elif shelf == "wishlist":
            base_query = base_query.order_by(
                func.coalesce(wishlist_subq.c.wishlist_at, wishlist_subq.c.w_added).is_(None),
                func.coalesce(wishlist_subq.c.wishlist_at, wishlist_subq.c.w_added).desc()
            )
        else:
            base_query = base_query.order_by(UserBook.created_at.is_(None), UserBook.created_at.desc())
    elif sort == "myRating":
        base_query = base_query.order_by(my_rating_subq.c.my_rating.desc().nullslast())
    elif sort == "avgRating":
        base_query = base_query.order_by(review_agg_subq.c.avg_rating.desc().nullslast())
    elif sort == "title":
        base_query = base_query.order_by(Book.title.asc())
    else:
        raise HTTPException(status_code=400, detail="sort 값 오류")

    total = base_query.count()
    rows = base_query.offset(offset).limit(limit).all()

    # 미리 book_id 리스트 추출 (중복 제거)
    book_ids = list(set(r[0].id for r in rows))
    # 진행률 미리 조회
    progress_dict = {}
    if shelf in ("reading", "completed") and book_ids:
        progress_rows = db.query(UserBook.book_id, func.max(UserPage.end_page))\
            .join(UserBook, UserBook.id == UserPage.user_book_id)\
            .filter(UserBook.user_id == current_user.id, UserBook.book_id.in_(book_ids))\
            .group_by(UserBook.book_id).all()
        progress_dict = {bid: (max_end or 0) for bid, max_end in progress_rows}
    # authors 미리 조회
    authors_dict = {}
    if book_ids:
        from app.models import BookAuthor, Author
        author_rows = db.query(BookAuthor.book_id, Author.name)\
            .join(Author, BookAuthor.author_id == Author.id)\
            .filter(BookAuthor.book_id.in_(book_ids)).all()
        from collections import defaultdict
        authors_dict = defaultdict(list)
        for bid, name in author_rows:
            authors_dict[bid].append(name)
    # categories 미리 조회
    categories_dict = {}
    if book_ids:
        cat_rows = db.query(BookCategory.book_id, BookCategory.category_name)\
            .filter(BookCategory.book_id.in_(book_ids)).all()
        categories_dict = defaultdict(list)
        for bid, cname in cat_rows:
            categories_dict[bid].append(cname)
    # current_page 미리 조회
    current_page_dict = {}
    if book_ids:
        from app.models import ReadingSession, ReadingEvent
        # 최근 이벤트 기반 페이지
        event_rows = db.query(ReadingSession.book_id, func.max(ReadingEvent.page))\
            .join(ReadingEvent, ReadingEvent.session_id == ReadingSession.id)\
            .filter(ReadingSession.user_id == current_user.id, ReadingSession.book_id.in_(book_ids), ReadingEvent.page.isnot(None))\
            .group_by(ReadingSession.book_id).all()
        for bid, page in event_rows:
            if page is not None:
                current_page_dict[bid] = int(page)
    # 없으면 UserPage의 max(end_page)
    if book_ids:
        up_rows = db.query(UserBook.book_id, func.max(UserPage.end_page))\
            .join(UserBook, UserBook.id == UserPage.user_book_id)\
            .filter(UserBook.user_id == current_user.id, UserBook.book_id.in_(book_ids))\
            .group_by(UserBook.book_id).all()
        for bid, page in up_rows:
            if bid not in current_page_dict and page is not None:
                current_page_dict[bid] = int(page)

    items: List[BookLibraryItem] = []
    seen_book_ids = set()
    from pytz import timezone
    tz = timezone('Asia/Seoul')
    for r in rows:
        book: Book = r[0]
        if shelf in ("reading", "completed"):
            if book.id in seen_book_ids:
                continue
            seen_book_ids.add(book.id)
        ub_status = r[1]
        added_at = r[2]
        started_at = r[3] if len(r) > 3 else None
        completed_at = r[4] if len(r) > 4 else None
        wishlist_at = r[5] if shelf == "wishlist" else None
        avg_rating = r[6] if shelf == "wishlist" else r[5]
        review_count = (r[7] if shelf == "wishlist" else r[6]) or 0
        my_rating = r[8] if shelf == "wishlist" else r[7]
        review_created_date = r[8] if shelf == "rated" else None
        # 진행률
        progress_percent = None
        if ub_status in (ReadingStatus.READING, ReadingStatus.COMPLETED):
            if book.total_pages:
                max_end = progress_dict.get(book.id)
                if max_end and book.total_pages:
                    progress_percent = round((max_end / book.total_pages) * 100, 2)
        # current_page
        current_page = current_page_dict.get(book.id)
        # 책별 누적 독서 시간 계산
        total_reading_seconds = None
        from app.models import ReadingSession
        sessions = db.query(ReadingSession).filter(
            ReadingSession.user_id == current_user.id,
            ReadingSession.book_id == book.id
        ).all()
        total_reading_seconds = sum(s.total_seconds or 0 for s in sessions)
        items.append(
            BookLibraryItem(
                book=BookResponse(
                    id=book.id,
                    isbn=book.isbn_10,
                    title=book.title,
                    publisher=book.publisher,
                    published_date=(
                        book.published_date.isoformat() if isinstance(book.published_date, datetime.datetime)
                        else str(book.published_date) if isinstance(book.published_date, datetime.date)
                        else None
                    ),
                    language=book.language,
                    category=book.category,
                    total_pages=book.total_pages,
                    thumbnail=getattr(book, "thumbnail", None),
                    small_thumbnail=getattr(book, "small_thumbnail", None),
                    google_rating=getattr(book, "google_rating", None),
                    google_ratings_count=getattr(book, "google_ratings_count", None),
                    authors=authors_dict.get(book.id, []),
                    categories=categories_dict.get(book.id, []),
                ),
                status=str(ub_status) if ub_status else "WISHLIST" if shelf == "wishlist" else "UNKNOWN",
                added_at=to_seoul(added_at).isoformat() if to_seoul(added_at) else None,
                started_at=to_seoul(started_at).isoformat() if to_seoul(started_at) else None,
                completed_at=to_seoul(completed_at).isoformat() if to_seoul(completed_at) else None,
                wishlist_at=to_seoul(wishlist_at).isoformat() if to_seoul(wishlist_at) else None,
                my_rating=my_rating,
                avg_rating=float(avg_rating) if avg_rating is not None else None,
                review_count=review_count,
                progress_percent=progress_percent,
                current_page=current_page,
                total_reading_seconds=total_reading_seconds,
            )
        )
    return LibraryResponse(total=total, items=items)
