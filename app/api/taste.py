from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.core.auth import get_current_user
from app.database import get_db
from app.models import User, Review, Book

router = APIRouter(prefix="/taste", tags=["taste"])


@router.get("/overview")
def overview(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    total_reviews = db.query(func.count(Review.id)).filter(Review.user_id == user.id).scalar() or 0

    # 별점 분포(1~5)
    dist_pairs = (
        db.query(Review.rating, func.count(Review.id))
        .filter(Review.user_id == user.id)
        .group_by(Review.rating)
        .all()
    )
    dist = {str(k): int(v) for k, v in dist_pairs}
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
