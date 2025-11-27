from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.auth import get_current_user
from app.database import get_db
from app.models import Highlight, User, UserBook
from app.schemas.highlight import (
    HighlightCreateRequest,
    HighlightUpdateRequest,
    HighlightResponse,
)

router = APIRouter(prefix="/highlights", tags=["highlights"])


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


@router.post("/", response_model=HighlightResponse)
def create_highlight(
    payload: HighlightCreateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    ub = _get_or_create_user_book(db, current_user.id, payload.book_id)
    highlight = Highlight(
        user_book_id=ub.id,
        page=payload.page,
        sentence=payload.sentence,
        is_public=bool(payload.is_public or False),
    )
    db.add(highlight)
    db.commit()
    db.refresh(highlight)
    return highlight


@router.put("/{highlight_id}", response_model=HighlightResponse)
def update_highlight(
    highlight_id: int,
    payload: HighlightUpdateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    hl = (
        db.query(Highlight)
        .join(UserBook, UserBook.id == Highlight.user_book_id)
        .filter(Highlight.id == highlight_id, UserBook.user_id == current_user.id)
        .first()
    )
    if not hl:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="하이라이트를 찾을 수 없습니다")

    if payload.sentence is not None:
        hl.sentence = payload.sentence
    if payload.is_public is not None:
        hl.is_public = payload.is_public
    db.commit()
    db.refresh(hl)
    return hl


@router.delete("/{highlight_id}", status_code=204)
def delete_highlight(
    highlight_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    hl = (
        db.query(Highlight)
        .join(UserBook, UserBook.id == Highlight.user_book_id)
        .filter(Highlight.id == highlight_id, UserBook.user_id == current_user.id)
        .first()
    )
    if not hl:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="하이라이트를 찾을 수 없습니다")

    db.delete(hl)
    db.commit()
    return None


@router.get("/books/{book_id}", response_model=list[HighlightResponse])
def list_highlights_for_book(
    book_id: int,
    limit: int = 50,
    offset: int = 0,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    highlights = (
        db.query(Highlight)
        .join(UserBook, UserBook.id == Highlight.user_book_id)
        .filter(UserBook.user_id == current_user.id, UserBook.book_id == book_id)
        .order_by(Highlight.page.asc(), Highlight.id.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )
    return highlights
