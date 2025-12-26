from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy import func, cast, Integer

from app.core.auth import get_current_user
from app.database import get_db
from app.models import User, Review, Book, UserTaste
from app.schemas.taste import (
    TasteOptionsResponse,
    TasteSubmitRequest,
    UserTasteResponse,
    TasteStatusResponse,
    ALLOWED_CATEGORIES,
    ALLOWED_GENRES,
)

router = APIRouter(prefix="/taste", tags=["taste"])


@router.get("/overview")
def overview(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    total_reviews = db.query(func.count(Review.id)).filter(Review.user_id == user.id).scalar() or 0

    # 별점 분포(1~5)
    # rating은 Float일 수 있으므로 정수 버킷으로 집계
    dist_pairs = (
        db.query(cast(Review.rating, Integer), func.count(Review.id))
        .filter(Review.user_id == user.id)
        .group_by(cast(Review.rating, Integer))
        .all()
    )
    dist = {str(int(k)): int(v) for k, v in dist_pairs}
    for k in range(1, 6):
        dist.setdefault(str(k), 0)

    # 선호 태그(카테고리 기반)
    cat_counts = (
        db.query(Book.category, func.count())
        .join(Review, Review.book_id == Book.id)
        .filter(Review.user_id == user.id)
        .group_by(Book.category)
        .all()
    )
    tags = [
        {"tag": (c or "").split("/")[-1].strip(), "count": int(cnt)}
        for c, cnt in cat_counts
        if c
    ]

    return {
        "total_reviews": int(total_reviews),
        "rating_distribution": dist,
        "favorite_tags": tags,
    }


@router.get("/options", response_model=TasteOptionsResponse, summary="초기 취향 선택을 위한 카테고리/장르 옵션")
def taste_options():
    return TasteOptionsResponse(categories=ALLOWED_CATEGORIES, genres=ALLOWED_GENRES)


@router.get("/me", response_model=TasteStatusResponse, summary="사용자 취향 분석 여부 및 선택 결과")
def taste_me(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    taste = db.query(UserTaste).filter(UserTaste.user_id == user.id).first()
    if not taste:
        return TasteStatusResponse(analyzed=bool(user.taste_analyzed), preferences=None)
    return TasteStatusResponse(
        analyzed=bool(user.taste_analyzed),
        preferences=UserTasteResponse(categories=taste.categories, genres=taste.genres),
    )


@router.post("/submit", response_model=UserTasteResponse, summary="초기 취향(카테고리/장르) 제출")
def taste_submit(
    payload: TasteSubmitRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    # 이미 완료된 경우 재제출 막기 (필요 시 수정 허용 정책으로 변경 가능)
    if user.taste_analyzed:
        raise HTTPException(status_code=400, detail="이미 취향 분석이 완료되었습니다")

    # 검증
    invalid_categories = [c for c in payload.categories if c not in ALLOWED_CATEGORIES]
    invalid_genres = [g for g in payload.genres if g not in ALLOWED_GENRES]
    if invalid_categories or invalid_genres:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"유효하지 않은 값 - categories: {invalid_categories}, genres: {invalid_genres}",
        )

    # 중복 제거 & 순서 유지
    def dedup(seq):
        seen = set()
        out = []
        for x in seq:
            if x not in seen:
                out.append(x)
                seen.add(x)
        return out

    categories = dedup(payload.categories)
    genres = dedup(payload.genres)

    existing = db.query(UserTaste).filter(UserTaste.user_id == user.id).first()
    if existing:
        # 정책상 재제출 막고 있으므로 이 분기 거의 안옴
        existing.categories = categories
        existing.genres = genres
        taste_obj = existing
    else:
        taste_obj = UserTaste(user_id=user.id, categories=categories, genres=genres)
        db.add(taste_obj)

    # 사용자 플래그 업데이트
    user.taste_analyzed = True
    db.commit()
    db.refresh(taste_obj)

    return UserTasteResponse(categories=taste_obj.categories, genres=taste_obj.genres)
