from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.core.auth import get_current_user
from app.database import get_db
from app.models import Review, User, UserBook
from app.schemas.review import (
    ReviewCreateRequest,
    ReviewUpdateRequest,
    ReviewResponse,
    BookRatingSummary,
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

    # 사용자 1명당 책 1건의 리뷰만 허용한다면 아래 중복 체크 활성화 가능
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
    return review


@router.put("/{review_id}", response_model=ReviewResponse)
def update_review(
    review_id: int,
    payload: ReviewUpdateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    rv = db.query(Review).filter(Review.id == review_id, Review.user_id == current_user.id).first()
    if not rv:
        raise HTTPException(status_code=404, detail="리뷰를 찾을 수 없습니다")

    if payload.rating is not None:
        rv.rating = payload.rating
    if payload.content is not None:
        rv.content = payload.content
    if payload.is_spoiler is not None:
        rv.is_spoiler = payload.is_spoiler

    db.commit()
    db.refresh(rv)
    return rv


@router.delete("/{review_id}", status_code=204)
def delete_review(
    review_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    rv = db.query(Review).filter(Review.id == review_id, Review.user_id == current_user.id).first()
    if not rv:
        raise HTTPException(status_code=404, detail="리뷰를 찾을 수 없습니다")
    db.delete(rv)
    db.commit()
    return None


@router.get("/books/{book_id}", response_model=list[ReviewResponse])
def list_reviews_for_book(
    book_id: int,
    limit: int = 50,
    offset: int = 0,
    db: Session = Depends(get_db),
):
    reviews = (
        db.query(Review)
        .filter(Review.book_id == book_id)
        .order_by(Review.created_date.desc(), Review.id.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )
    return reviews


@router.get("/books/{book_id}/summary", response_model=BookRatingSummary)
def get_book_rating_summary(book_id: int, db: Session = Depends(get_db)):
    avg, count = db.query(func.avg(Review.rating), func.count(Review.id)).filter(Review.book_id == book_id).one()
    return BookRatingSummary(book_id=book_id, average_rating=float(avg) if avg is not None else None, review_count=count)
