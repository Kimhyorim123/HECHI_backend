from datetime import datetime, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy import func
from pydantic import BaseModel, Field

from app.core.auth import get_current_user
from app.database import get_db
from app.models import (
    User,
    SearchHistory,
    BookView,
    Book,
    Review,
    ReadingSession,
    BookCategory,
    UserInsight,
    UserBook,
)
from app.schemas.calendar import CalendarMonthResponse, CalendarDay, CalendarBookItem

router = APIRouter(prefix="/analytics", tags=["analytics"])


class SearchLogRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=255)


class ViewLogRequest(BaseModel):
    book_id: int


class RatingBucket(BaseModel):
    rating: float
    count: int


class RatingSummary(BaseModel):
    average_5: float
    average_100: int
    total_reviews: int
    most_frequent_rating: Optional[float] = None
    total_comments: int


class GenreStat(BaseModel):
    name: str
    review_count: int
    average_5: float
    average_100: int


class ReadingTime(BaseModel):
    total_seconds: int
    human: str


class UserStatsResponse(BaseModel):
    rating_distribution: List[RatingBucket]
    rating_summary: RatingSummary
    reading_time: ReadingTime
    top_level_genres: List[GenreStat]
    sub_genres: List[GenreStat]


# =============================
# 사용자 인사이트 (임시 AI 대체 데이터)
# =============================


class InsightTag(BaseModel):
    label: str
    weight: float = Field(ge=0.0, le=1.0, description="0~1 가중치")


class UserInsightResponse(BaseModel):
    analysis: str | None = None
    tags: List[InsightTag] = []


class UserInsightUpsert(BaseModel):
    analysis: str | None = None
    tags: List[InsightTag] | None = None


@router.post("/search", status_code=status.HTTP_201_CREATED)
def log_search(
    data: SearchLogRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    entry = SearchHistory(user_id=user.id, query=data.query, created_at=datetime.now(timezone.utc))
    db.add(entry)
    db.commit()
    return {"ok": True}


@router.post("/views", status_code=status.HTTP_201_CREATED)
def log_view(
    data: ViewLogRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    # 책 존재 확인(Optional): 없으면 404
    exists = db.query(Book.id).filter(Book.id == data.book_id).first()
    if not exists:
        raise HTTPException(status_code=404, detail="Book not found")

    entry = BookView(book_id=data.book_id, user_id=user.id, created_at=datetime.now(timezone.utc))
    db.add(entry)
    db.commit()
    return {"ok": True}


# =============================
# 사용자 통계 엔드포인트
# =============================

TOP_LEVEL_GENRES = ["소설", "시", "에세이", "만화", "웹툰"]
# 세부 장르는 개별 항목 + 그룹 묶음(합산 표시)
SUB_GENRES = [
    "추리",
    "스릴러",
    "공포",
    "SF",
    "판타지",
    "로맨스",
    "액션",
    "역사",
    "과학",
    "인문",
    "철학",
    "사회",
    "경제",
    "경영",
    "자기계발",
    "예술",
    "여행",
    "코미디",
]
# 그룹 표시용: (표시명, [멤버들])
SUB_GENRE_GROUPS: list[tuple[str, list[str]]] = [
    ("경제/경영", ["경제", "경영"]),
]

# 현재 DB의 영어 주제 분류를 한국어 장르로 매핑
# 필요 시 확장 가능. 존재하지 않는 키는 매칭하지 않음.
CATEGORY_TO_TOP_LEVEL: dict[str, str] = {
    # 대표 매핑 예시
    "Fiction": "소설",
    "Juvenile Fiction": "소설",
    "Korean fiction": "소설",
    "Juvenile Nonfiction": "에세이",  # 임시 분류
    "Literary Collections": "소설",
    "Literary Criticism": "소설",
    "Comics & Graphic Novels": "만화",
    "Poetry": "시",
    # 보조 매핑(표기용 대분류)
    "Essays": "에세이",
    "Comics": "만화",
    "Graphic Novels": "만화",
}

CATEGORY_TO_SUB_GENRE: dict[str, str] = {
    # 기존 매핑
    "Science": "과학",
    "Philosophy": "철학",
    "Self-Help": "자기계발",
    "Business & Economics": "경제",
    "Management": "경영",
    "Computers": "SF",
    "Education": "인문",
    "History": "역사",
    "Travel": "여행",
    "Art": "예술",
    "Psychology": "자기계발",
    "Foreign Language Study": "인문",
    "Social Science": "사회",
    "Study Aids": "인문",
    "England": "역사",
    "Korean fiction": "로맨스",
    "Literary Collections": "추리",
    "Literary Criticism": "추리",
    # 새로운 매핑 추가
    "Action": "액션",
    "Comedy": "코미디",
    "Politics": "사회",
    "Fine Arts": "예술",
    "Performing Arts": "예술",
    "Graphic Novels": "코미디",
    "Drama": "코미디",
}


def _humanize_seconds(total: int) -> str:
    if total <= 0:
        return "0시간"
    hours = total // 3600
    minutes = (total % 3600) // 60
    if hours and minutes:
        return f"총 {hours}시간 {minutes}분 감상하였습니다."
    if hours:
        return f"총 {hours}시간 감상하였습니다."
    return f"총 {minutes}분 감상하였습니다."


@router.get(
    "/my-stats",
    response_model=UserStatsResponse,
    summary="사용자 독서/평점/선호 통계",
    description=(
        "선호 장르 UI는 sub_genres를 사용하세요. "
        "top_level_genres는 대분류(소설/시/에세이/만화/웹툰)로 표기용입니다. "
        "모든 집계는 사용자 평점이 있는 리뷰만 포함되며, 반환 목록은 평균점수와 편수 기준으로 내림차순 정렬됩니다."
    ),
)
def user_stats(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    # 평점 분포 (0.5 간격으로 0 채움 포함)
    rows = (
        db.query((func.round(Review.rating * 2) / 2).label("bucket"), func.count(Review.id))
        .filter(Review.user_id == user.id, Review.rating != None)
        .group_by("bucket")
        .all()
    )
    bucket_counts: dict[float, int] = {float(b): int(c) for b, c in rows if b is not None}
    distribution: list[RatingBucket] = []
    v = 0.5
    total_reviews = 0
    while v <= 5.0 + 1e-9:
        cnt = bucket_counts.get(round(v, 1), 0)
        total_reviews += cnt
        distribution.append(RatingBucket(rating=round(v, 1), count=cnt))
        v += 0.5
    # 요약 정보 (평균은 실제 값 기준)
    avg_row = (
        db.query(func.avg(Review.rating))
        .filter(Review.user_id == user.id, Review.rating != None)
        .one()
    )
    avg_val = avg_row[0]
    avg_5 = round(float(avg_val), 2) if avg_val is not None else 0.0
    avg_100 = int(round(avg_5 * 20))
    most_frequent_rating = None
    if bucket_counts:
        most_frequent_rating = max(bucket_counts.items(), key=lambda x: x[1])[0]
    # 전체 코멘트 개수 집계
        total_comments = db.query(func.count()).select_from(ReviewComment).join(Review, ReviewComment.review_id == Review.id).filter(Review.user_id == user.id).scalar()

    rating_summary = RatingSummary(
        average_5=avg_5,
        average_100=avg_100,
        total_reviews=total_reviews,
        most_frequent_rating=most_frequent_rating,
        total_comments=total_comments,
    )

    # 독서 감상 시간 (ReadingSession 기준)
    session_rows = (
        db.query(ReadingSession.start_time, ReadingSession.end_time, ReadingSession.total_seconds)
        .filter(ReadingSession.user_id == user.id)
        .all()
    )
    total_seconds = 0
    for start, end, total in session_rows:
        if total is not None:
            total_seconds += total
        elif start and end:
            diff = int((end - start).total_seconds())
            if diff > 0:
                total_seconds += diff
    reading_time = ReadingTime(total_seconds=total_seconds, human=_humanize_seconds(total_seconds))

    # 장르 통계 (BookCategory 기반)
    # 리뷰를 기준으로 사용자가 평가한 책들의 카테고리 매칭
    # 한 책이 여러 카테고리를 가지면 각각에 카운트 반영
    category_rows = (
        db.query(Book.category, Review.rating)
        .join(Review, Review.book_id == Book.id)
        .filter(Review.user_id == user.id, Review.rating != None)
        .all()
    )

    # 장르 누적 버킷(표시용 이름 기준)
    top_acc: dict[str, dict] = {}
    sub_acc: dict[str, dict] = {}

    def _accumulate(bucket: dict[str, dict], name: str, rating: float):
        bucket.setdefault(name, {"sum": 0.0, "count": 0})
        bucket[name]["sum"] += rating
        bucket[name]["count"] += 1

    for cat, rating in category_rows:
        if not cat:
            continue
        # Top-level 매핑
        tl = CATEGORY_TO_TOP_LEVEL.get(cat)
        if tl:
            _accumulate(top_acc, tl, rating)
        # Sub-genre 매핑
        sg = CATEGORY_TO_SUB_GENRE.get(cat)
        if sg:
            _accumulate(sub_acc, sg, rating)

    def build_stats_with_zeros_from(bucket: dict[str, dict], names: list[str]) -> List[GenreStat]:
        out = []
        for name in names:
            data = bucket.get(name)
            if not data:
                out.append(
                    GenreStat(
                        name=name,
                        review_count=0,
                        average_5=0.0,
                        average_100=0,
                    )
                )
            else:
                avg5 = round(data["sum"] / data["count"], 2)
                out.append(
                    GenreStat(
                        name=name,
                        review_count=data["count"],
                        average_5=avg5,
                        average_100=int(round(avg5 * 20)),
                    )
                )
        # 내림차순: 평균 점수 우선, 리뷰 수 보조
        out.sort(key=lambda x: (x.average_5, x.review_count), reverse=True)
        return out

    def build_group_stats_from(bucket: dict[str, dict], groups: list[tuple[str, list[str]]]) -> List[GenreStat]:
        out = []
        for display, members in groups:
            ssum = 0.0
            scount = 0
            for m in members:
                d = bucket.get(m)
                if d:
                    ssum += d["sum"]
                    scount += d["count"]
            if scount == 0:
                out.append(
                    GenreStat(
                        name=display,
                        review_count=0,
                        average_5=0.0,
                        average_100=0,
                    )
                )
            else:
                avg5 = round(ssum / scount, 2)
                out.append(
                    GenreStat(
                        name=display,
                        review_count=scount,
                        average_5=avg5,
                        average_100=int(round(avg5 * 20)),
                    )
                )
        out.sort(key=lambda x: (x.average_5, x.review_count), reverse=True)
        return out

    top_level = build_stats_with_zeros_from(top_acc, TOP_LEVEL_GENRES)
    # 세부 장르는 개별 + 그룹 결과를 합쳐서 제공
    sub_individual = build_stats_with_zeros_from(sub_acc, SUB_GENRES)
    sub_grouped = build_group_stats_from(sub_acc, SUB_GENRE_GROUPS)
    sub_level = sorted(sub_individual + sub_grouped, key=lambda x: (x.average_5, x.review_count), reverse=True)

    return UserStatsResponse(
        rating_distribution=distribution,
        rating_summary=rating_summary,
        reading_time=reading_time,
        top_level_genres=top_level,
        sub_genres=sub_level,
    )


@router.get("/my-insights", response_model=UserInsightResponse, summary="사용자 인사이트/태그 (임시 AI 대체)")
def my_insights(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    row = db.query(UserInsight).filter(UserInsight.user_id == user.id).first()
    if not row:
        return UserInsightResponse(analysis=None, tags=[])
    tags = []
    if row.tags:
        for t in row.tags:
            label = t.get("label")
            weight = t.get("weight", 0.0)
            if label:
                tags.append(InsightTag(label=label, weight=float(weight)))
    return UserInsightResponse(analysis=row.analysis_text, tags=tags)


@router.post("/my-insights", response_model=UserInsightResponse, summary="사용자 인사이트/태그 업서트(임시 저장)")
def upsert_my_insights(
    data: UserInsightUpsert,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    row = db.query(UserInsight).filter(UserInsight.user_id == user.id).first()
    payload_tags = None
    if data.tags is not None:
        payload_tags = [{"label": t.label, "weight": float(t.weight)} for t in data.tags]
    if not row:
        row = UserInsight(
            user_id=user.id,
            analysis_text=data.analysis,
            tags=payload_tags,
        )
        db.add(row)
    else:
        if data.analysis is not None:
            row.analysis_text = data.analysis
        if payload_tags is not None:
            row.tags = payload_tags
    db.commit()
    # 반환
    out_tags = []
    if row.tags:
        out_tags = [InsightTag(label=t["label"], weight=float(t.get("weight", 0.0))) for t in row.tags if t.get("label")]
    return UserInsightResponse(analysis=row.analysis_text, tags=out_tags)


@router.get("/calendar-month", response_model=CalendarMonthResponse, summary="월간 독서 캘린더 요약 + 평점 남긴 책 표지")
def calendar_month(
    year: int,
    month: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """
    주어진 월에 사용자가 평점을 남긴 책을 캘린더에 표시합니다.
    - 평점 남긴 날짜를 기준으로 책을 표시합니다.
    - 최다 장르를 계산하여 반환합니다.
    """
    from datetime import date
    from calendar import monthrange
    start = date(year, month, 1)
    last_day = monthrange(year, month)[1]
    end = date(year, month, last_day)

    # 평점 남긴 책 기준으로 조회
    rated_books = (
        db.query(Review.book_id, Review.created_date)
        .filter(Review.user_id == user.id, Review.created_date >= start, Review.created_date <= end, Review.rating != None)
        .all()
    )
    book_ids = [bid for (bid, _) in rated_books]
    total_rated_count = len(book_ids)

    # 최다 장르
    top_genre = None
    if book_ids:
        from collections import Counter
        cats = db.query(Book.category).filter(Book.id.in_(book_ids)).all()
        cnt = Counter([c for (c,) in cats if c])
        if cnt:
            top_genre = cnt.most_common(1)[0][0]

    # 평점 남긴 책만 캘린더에 표지 표시 (평점 남긴 날짜 기준)
    # Book, authors, rating 한 번에 조회
    books = db.query(Book).filter(Book.id.in_(book_ids)).all()
    # book_id -> [author_name, ...]
    author_map = {b.id: [ba.author.name for ba in b.authors] for b in books}
    # 내 별점 맵
    rating_map = {r.book_id: r.rating for r in db.query(Review.book_id, Review.rating).filter(Review.user_id == user.id, Review.book_id.in_(book_ids)).all()}
    books_map = {b.id: b for b in books}
    by_date: dict[str, list[CalendarBookItem]] = {}
    for (bid, rdate) in rated_books:
        if rdate:
            b = books_map.get(bid)
            if not b:
                continue
            key = rdate.isoformat()
            by_date.setdefault(key, []).append(
                CalendarBookItem(
                    book_id=bid,
                    title=b.title,
                    thumbnail=getattr(b, "thumbnail", None),
                    authors=author_map.get(bid, []),
                    rating=rating_map.get(bid)
                )
            )

    days = [CalendarDay(date=d, items=items) for d, items in sorted(by_date.items())]
    return CalendarMonthResponse(year=year, month=month, total_read_count=total_rated_count, top_genre=top_genre, days=days)
