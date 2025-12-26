from app.core.utils import to_seoul
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.core.auth import get_current_user
from app.database import get_db
from app.models import Review, User, UserBook, ReviewLike, ReviewComment
from app.schemas.review import (
    ReviewCreateRequest,
    ReviewUpdateRequest,
    ReviewResponse,
    BookRatingSummary,
    RatingBucket,
    ReviewUpsertRequest,
    CommentCreateRequest,
    CommentResponse,
)

router = APIRouter(prefix="/reviews", tags=["reviews"])


def _get_or_create_user_book(db: Session, user_id: int, book_id: int) -> UserBook:
    ub = (
        db.query(UserBook)
        .filter(UserBook.user_id == user_id, UserBook.book_id == book_id)
        .first()
    )
    if ub:
        return ub
    ub = UserBook(user_id=user_id, book_id=book_id)
    db.add(ub)
    db.commit()
    db.refresh(ub)
    return ub


@router.post("/", response_model=ReviewResponse)
def create_review(
    payload: ReviewCreateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    ub = _get_or_create_user_book(db, current_user.id, payload.book_id)

    existing = (
        db.query(Review)
        .filter(Review.user_id == current_user.id, Review.book_id == payload.book_id)
        .first()
    )
    if existing:
        raise HTTPException(status_code=400, detail="이미 리뷰를 작성했습니다")

    review = Review(
        user_book_id=ub.id,
        user_id=current_user.id,
        book_id=payload.book_id,
        rating=payload.rating,
        content=payload.content,
        is_spoiler=payload.is_spoiler,
    )
    db.add(review)
    db.commit()
    db.refresh(review)

    resp = ReviewResponse.model_validate(review)
    resp.created_date = to_seoul(resp.created_date)
    resp.is_my_review = True
    return resp


@router.post("/upsert", response_model=ReviewResponse, summary="리뷰 생성 또는 갱신")
def upsert_review(
    payload: ReviewUpsertRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    ub = _get_or_create_user_book(db, current_user.id, payload.book_id)

    rv = (
        db.query(Review)
        .filter(Review.user_id == current_user.id, Review.book_id == payload.book_id)
        .first()
    )
    if rv:
        fields_set = payload.model_fields_set
        if "rating" in fields_set:
            rv.rating = payload.rating
        if "content" in fields_set:
            rv.content = (
                payload.content
                if (payload.content and payload.content.strip() != "")
                else None
            )
        if "is_spoiler" in fields_set and payload.is_spoiler is not None:
            rv.is_spoiler = payload.is_spoiler
        db.commit()
        db.refresh(rv)
        resp = ReviewResponse.model_validate(rv)
        resp.created_date = to_seoul(resp.created_date)
        resp.is_my_review = True
        return resp

    review = Review(
        user_book_id=ub.id,
        user_id=current_user.id,
        book_id=payload.book_id,
        rating=payload.rating,
        content=payload.content,
        is_spoiler=payload.is_spoiler,
    )
    db.add(review)
    db.commit()
    db.refresh(review)
    resp = ReviewResponse.model_validate(review)
    resp.created_date = to_seoul(resp.created_date)
    resp.is_my_review = True
    return resp


@router.patch(
    "/rating",
    response_model=ReviewResponse,
    summary="별점만 갱신 (Deprecated)",
    deprecated=True,
)
def update_rating_only(
    book_id: int,
    rating: float,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    ub = _get_or_create_user_book(db, current_user.id, book_id)
    rv = (
        db.query(Review)
        .filter(Review.user_id == current_user.id, Review.book_id == book_id)
        .first()
    )
    if rv:
        rv.rating = rating
        db.commit()
        db.refresh(rv)
        resp = ReviewResponse.model_validate(rv)
        resp.created_date = to_seoul(resp.created_date)
        resp.is_my_review = True
        return resp

    review = Review(
        user_book_id=ub.id,
        user_id=current_user.id,
        book_id=book_id,
        rating=rating,
        content=None,
        is_spoiler=False,
    )
    db.add(review)
    db.commit()
    db.refresh(review)
    resp = ReviewResponse.model_validate(review)
    resp.created_date = to_seoul(resp.created_date)
    resp.is_my_review = True
    return resp


@router.put("/{review_id}", response_model=ReviewResponse)
def update_review(
    review_id: int,
    payload: ReviewUpdateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    rv = (
        db.query(Review)
        .filter(Review.id == review_id, Review.user_id == current_user.id)
        .first()
    )
    if not rv:
        raise HTTPException(status_code=404, detail="리뷰를 찾을 수 없습니다")

    fields_set = payload.model_fields_set
    if "rating" in fields_set:
        rv.rating = payload.rating
    if "content" in fields_set:
        rv.content = (
            payload.content
            if (payload.content and payload.content.strip() != "")
            else None
        )
    if "is_spoiler" in fields_set and payload.is_spoiler is not None:
        rv.is_spoiler = payload.is_spoiler

    db.commit()
    db.refresh(rv)
    resp = ReviewResponse.model_validate(rv)
    resp.created_date = to_seoul(resp.created_date)
    resp.is_my_review = True
    return resp


@router.delete("/{review_id}", status_code=204)
def delete_review(
    review_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    rv = (
        db.query(Review)
        .filter(Review.id == review_id, Review.user_id == current_user.id)
        .first()
    )
    if not rv:
        raise HTTPException(status_code=404, detail="리뷰를 찾을 수 없습니다")
    db.delete(rv)
    db.commit()
    return None


@router.get("/books/{book_id}", response_model=list[ReviewResponse], summary="특정 책의 리뷰 목록")
def list_reviews_for_book(
    book_id: int,
    limit: int = 50,
    offset: int = 0,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    reviews = (
        db.query(Review)
        .filter(Review.book_id == book_id)
        .order_by(Review.created_date.desc(), Review.id.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )

    review_ids = [rv.id for rv in reviews]
    liked_set: set[int] = set()
    if review_ids:
        liked_rows = (
            db.query(ReviewLike.review_id)
            .filter(
                ReviewLike.review_id.in_(review_ids),
                ReviewLike.user_id == current_user.id,
            )
            .all()
        )
        liked_set = {rid for (rid,) in liked_rows}

    # 책 전체 코멘트 수
    book_comment_count = (
        db.query(func.count(ReviewComment.id))
        .join(Review, Review.id == ReviewComment.review_id)
        .filter(Review.book_id == book_id)
        .scalar()
    ) or 0

    # 유저 전체 코멘트 수
    user_comment_count = (
        db.query(func.count(ReviewComment.id))
        .filter(ReviewComment.user_id == current_user.id)
        .scalar()
    ) or 0

    # 각 리뷰별 댓글 수
    comment_counts = {}
    if review_ids:
        comment_rows = (
            db.query(ReviewComment.review_id, func.count(ReviewComment.id))
            .filter(ReviewComment.review_id.in_(review_ids))
            .group_by(ReviewComment.review_id)
            .all()
        )
        comment_counts = {rid: cnt for (rid, cnt) in comment_rows}

    # 작성자 닉네임
    user_ids = {rv.user_id for rv in reviews}
    user_map = {
        u.id: u.nickname
        for u in db.query(User).filter(User.id.in_(user_ids)).all()
    }

    out: list[ReviewResponse] = []
    for rv in reviews:
        item = ReviewResponse.model_validate(rv)
        item.created_date = to_seoul(item.created_date)
        item.is_my_review = bool(rv.user_id == current_user.id)
        item.is_liked = rv.id in liked_set
        item.book_comment_count = book_comment_count
        item.user_comment_count = user_comment_count
        item.comment_count = comment_counts.get(rv.id, 0)
        item.nickname = user_map.get(rv.user_id)
        out.append(item)
    return out


@router.get("/books/{book_id}/summary", response_model=BookRatingSummary)
def get_book_rating_summary(book_id: int, db: Session = Depends(get_db)):
    avg, count = (
        db.query(func.avg(Review.rating), func.count(Review.id))
        .filter(Review.book_id == book_id, Review.rating != None)
        .one()
    )
    return BookRatingSummary(
        book_id=book_id,
        average_rating=float(avg) if avg is not None else None,
        review_count=count,
    )


@router.get(
    "/books/{book_id}/distribution",
    response_model=list[RatingBucket],
    summary="특정 책의 0.5 간격 평점 분포",
)
def get_book_rating_distribution(
    book_id: int,
    db: Session = Depends(get_db),
):
    rows = (
        db.query((func.round(Review.rating * 2) / 2).label("bucket"), func.count(Review.id))
        .filter(Review.book_id == book_id, Review.rating != None)
        .group_by("bucket")
        .all()
    )
    counts = {float(bucket): int(cnt) for bucket, cnt in rows if bucket is not None}
    out: list[RatingBucket] = []
    v = 0.5
    while v <= 5.0 + 1e-9:
        r = round(v, 1)
        out.append(RatingBucket(rating=r, count=counts.get(r, 0)))
        v += 0.5
    return out


@router.get("/{review_id}", response_model=ReviewResponse, summary="리뷰 상세")
def get_review_detail(
    review_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    rv = db.query(Review).filter(Review.id == review_id).first()
    if not rv:
        raise HTTPException(status_code=404, detail="리뷰를 찾을 수 없습니다")

    try:
        resp = ReviewResponse.model_validate(rv)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"ReviewResponse 변환 오류: {e}")

    resp.created_date = to_seoul(resp.created_date)
    resp.is_my_review = rv.user_id == current_user.id

    liked = (
        db.query(ReviewLike)
        .filter(ReviewLike.review_id == review_id, ReviewLike.user_id == current_user.id)
        .first()
    )
    resp.is_liked = bool(liked)

    comment_count = (
        db.query(func.count(ReviewComment.id))
        .filter(ReviewComment.review_id == review_id)
        .scalar()
    ) or 0
    resp.comment_count = int(comment_count)

    user = db.query(User).filter(User.id == rv.user_id).first()
    resp.nickname = user.nickname if user else None

    rating_count = (
        db.query(func.count(Review.rating))
        .filter(Review.id == review_id, Review.rating != None)
        .scalar()
    ) or 0
    resp.rating_count = int(rating_count)

    book_comment_count = (
        db.query(func.count(ReviewComment.id))
        .join(Review, Review.id == ReviewComment.review_id)
        .filter(Review.book_id == rv.book_id)
        .scalar()
    ) or 0
    resp.book_comment_count = int(book_comment_count)

    user_comment_count = (
        db.query(func.count(ReviewComment.id))
        .join(Review, Review.id == ReviewComment.review_id)
        .filter(Review.user_id == rv.user_id)
        .scalar()
    ) or 0
    resp.user_comment_count = int(user_comment_count)

    return resp


@router.post("/{review_id}/like", summary="리뷰 좋아요 토글")
def toggle_like_review(
    review_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    rv = db.query(Review).filter(Review.id == review_id).first()
    if not rv:
        raise HTTPException(status_code=404, detail="리뷰를 찾을 수 없습니다")

    existing = (
        db.query(ReviewLike)
        .filter(ReviewLike.review_id == review_id, ReviewLike.user_id == current_user.id)
        .first()
    )
    if existing:
        db.delete(existing)
        rv.like_count = max(0, (rv.like_count or 0) - 1)
        db.commit()
        db.refresh(rv)
        return {"liked": False, "like_count": rv.like_count}

    like = ReviewLike(review_id=review_id, user_id=current_user.id)
    db.add(like)
    rv.like_count = (rv.like_count or 0) + 1
    db.commit()
    db.refresh(rv)
    return {"liked": True, "like_count": rv.like_count}


@router.get("/{review_id}/comments", response_model=list[CommentResponse], summary="리뷰 댓글 목록")
def list_review_comments(
    review_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    rv = db.query(Review).filter(Review.id == review_id).first()
    if not rv:
        raise HTTPException(status_code=404, detail="리뷰를 찾을 수 없습니다")
    comments = (
        db.query(ReviewComment)
        .filter(ReviewComment.review_id == review_id)
        .order_by(ReviewComment.created_at.asc(), ReviewComment.id.asc())
        .all()
    )
    out = []
    for c in comments:
        item = CommentResponse.model_validate(c)
        item.created_at = to_seoul(item.created_at)
        out.append(item)
    return out


@router.post("/{review_id}/comments", response_model=CommentResponse, summary="리뷰 댓글 작성")
def create_review_comment(
    review_id: int,
    payload: CommentCreateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    rv = db.query(Review).filter(Review.id == review_id).first()
    if not rv:
        raise HTTPException(status_code=404, detail="리뷰를 찾을 수 없습니다")
    comment = ReviewComment(
        review_id=review_id,
        user_id=current_user.id,
        content=payload.content,
    )
    db.add(comment)
    db.commit()
    db.refresh(comment)
    item = CommentResponse.model_validate(comment)
    item.created_at = to_seoul(item.created_at)
    return item


@router.delete("/comments/{comment_id}", status_code=204, summary="리뷰 댓글 삭제")
def delete_review_comment(
    comment_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    c = (
        db.query(ReviewComment)
        .filter(ReviewComment.id == comment_id, ReviewComment.user_id == current_user.id)
        .first()
    )
    if not c:
        raise HTTPException(status_code=404, detail="댓글을 찾을 수 없거나 권한이 없습니다")
    db.delete(c)
    db.commit()
    return None
