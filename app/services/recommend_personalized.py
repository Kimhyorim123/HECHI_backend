from sqlalchemy.orm import Session
from typing import List, Tuple
from datetime import datetime, timedelta

from app.models import (
    User,
    Review,
    Book,
    UserBook,
    Wishlist,
    SearchHistory,
)
from app.services.genre_mapping import get_korean_genres


def _get_preferred_genres_and_authors(db: Session, user_id: int) -> Tuple[set, set]:
    genres: set = set()
    authors: set = set()
    # 고평점 리뷰 기반(별점 >= 4.0)
    liked = (
        db.query(Review)
        .filter(Review.user_id == user_id)
        .filter(Review.rating != None)
        .filter(Review.rating >= 4.0)
        .all()
    )
    for r in liked:
        b = db.query(Book).filter(Book.id == r.book_id).first()
        if not b:
            continue
        # Book.category → 한글 장르 매핑
        if getattr(b, "category", None):
            for g in get_korean_genres(b.category):
                genres.add(g)
        # authors 필드는 문자열 배열로 저장되어 있을 수 있음
        if getattr(b, "authors", None):
            for a in b.authors or []:
                authors.add(a)
    return genres, authors


def _get_recent_search_keywords(db: Session, user_id: int, days: int = 30) -> List[str]:
    cutoff = datetime.utcnow() - timedelta(days=days)
    rows = (
        db.query(SearchHistory)
        .filter(SearchHistory.user_id == user_id)
        .filter(SearchHistory.created_at >= cutoff)
        .order_by(SearchHistory.id.desc())
        .limit(50)
        .all()
    )
    return [r.query for r in rows]


def _is_excluded(db: Session, user_id: int, book_id: int) -> bool:
    # 읽은/평점/리뷰/위시/보관함 담김 제외
    if db.query(UserBook).filter(UserBook.user_id == user_id, UserBook.book_id == book_id).first():
        return True
    if db.query(Review).filter(Review.user_id == user_id, Review.book_id == book_id).first():
        return True
    if db.query(Wishlist).filter(Wishlist.user_id == user_id, Wishlist.book_id == book_id).first():
        return True
    return False


def _score_book(b: Book, pref_genres: set, pref_authors: set, keywords: List[str]) -> float:
    score = 0.0
    # 장르 적합 (한글 장르 매핑)
    if getattr(b, "category", None):
        genres = set(get_korean_genres(b.category))
        if genres & pref_genres:
            score += 1.0
    # 저자 선호
    if getattr(b, "authors", None):
        if any(a in pref_authors for a in (b.authors or [])):
            score += 0.8
    # 키워드 매칭(제목/출판사/카테고리에 간단 포함 검사)
    title = (b.title or "").lower()
    publisher = (b.publisher or "").lower()
    category = (b.category or "").lower()
    for kw in keywords:
        k = kw.lower()
        if k in title or k in publisher or k in category:
            score += 0.7
            break
    return score


def get_personalized_books(db: Session, user: User, limit: int = 20, offset: int = 0) -> List[Book]:
    pref_genres, pref_authors = _get_preferred_genres_and_authors(db, user.id)
    keywords = _get_recent_search_keywords(db, user.id)

    # 간단 후보군: 장르/저자/키워드 유사한 책들 우선적으로 수집
    q = db.query(Book)
    # 후보군: BookCategory 테이블에서 pref_genres와 매핑되는 book_id 추출
    candidates = []
    if pref_genres:
        # BookCategory.category_name → 한글 장르 매핑 후 pref_genres와 교집합이 있으면 후보
        from app.models import BookCategory
        book_ids = set()
        for bc in db.query(BookCategory).all():
            genres = set(get_korean_genres(bc.category_name))
            if genres & pref_genres:
                book_ids.add(bc.book_id)
        if book_ids:
            candidates = db.query(Book).filter(Book.id.in_(book_ids)).limit(500).all()
        else:
            candidates = q.limit(500).all()
    else:
        candidates = q.limit(500).all()

    # 점수화 + 제외 적용
    scored: List[Tuple[float, Book]] = []
    for b in candidates:
        if _is_excluded(db, user.id, b.id):
            continue
        s = _score_book(b, pref_genres, pref_authors, keywords)
        if s > 0:
            scored.append((s, b))

    # 정렬 및 다양성(저자/장르 상한 간단 적용)
    scored.sort(key=lambda t: t[0], reverse=True)
    out: List[Book] = []
    author_count: dict = {}
    genre_count: dict = {}
    M_AUTHOR = 2
    M_GENRE = 3
    for _, b in scored:
        # 저자 상한
        authors = b.authors or []
        genres = set(get_korean_genres(b.category or ""))
        if authors:
            if any(author_count.get(a, 0) >= M_AUTHOR for a in authors):
                continue
        # 장르별 상한 적용 (여러 장르 중 하나라도 초과 시 제외)
        if genres:
            if any(genre_count.get(g, 0) >= M_GENRE for g in genres):
                continue
        out.append(b)
        for a in authors:
            author_count[a] = author_count.get(a, 0) + 1
        for g in genres:
            genre_count[g] = genre_count.get(g, 0) + 1
        if len(out) >= (limit + offset):
            break

    return out[offset: offset + limit]
