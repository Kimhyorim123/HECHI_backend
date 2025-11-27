from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.auth import get_current_user
from app.database import get_db
from app.models import Bookmark, User, UserBook
from app.schemas.bookmark import BookmarkCreateRequest, BookmarkResponse

router = APIRouter(prefix="/bookmarks", tags=["bookmarks"])


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


@router.post("/", response_model=BookmarkResponse)
def create_bookmark(
    payload: BookmarkCreateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    ub = _get_or_create_user_book(db, current_user.id, payload.book_id)
    bookmark = Bookmark(user_book_id=ub.id, page=payload.page, memo=payload.memo)
    db.add(bookmark)
    db.commit()
    db.refresh(bookmark)
    return bookmark


@router.delete("/{bookmark_id}", status_code=204)
def delete_bookmark(
    bookmark_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    bm = (
        db.query(Bookmark)
        .join(UserBook, UserBook.id == Bookmark.user_book_id)
        .filter(Bookmark.id == bookmark_id, UserBook.user_id == current_user.id)
        .first()
    )
    if not bm:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="북마크를 찾을 수 없습니다")

    db.delete(bm)
    db.commit()
    return None


@router.get("/books/{book_id}", response_model=list[BookmarkResponse])
def list_bookmarks_for_book(
    book_id: int,
    limit: int = 50,
    offset: int = 0,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    bookmarks = (
        db.query(Bookmark)
        .join(UserBook, UserBook.id == Bookmark.user_book_id)
        .filter(UserBook.user_id == current_user.id, UserBook.book_id == book_id)
        .order_by(Bookmark.page.asc(), Bookmark.id.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )
    return bookmarks
