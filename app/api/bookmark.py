from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.auth import get_current_user
from app.database import get_db
from app.models import Bookmark, User, UserBook
from app.schemas.bookmark import BookmarkCreateRequest, BookmarkResponse, BookmarkUpdateRequest
from app.core.utils import to_seoul

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
    # created_date 변환 적용
    bookmark.created_date = to_seoul(bookmark.created_date)
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


@router.put("/{bookmark_id}", response_model=BookmarkResponse)
def update_bookmark(
    bookmark_id: int,
    payload: BookmarkUpdateRequest,
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
    # 페이지/메모 부분 업데이트 허용. 메모는 명시적 null도 허용
    provided = payload.model_dump(exclude_unset=True)
    if "page" in provided:
        bm.page = payload.page  # type: ignore
    if "memo" in provided:
        bm.memo = payload.memo
    db.commit()
    db.refresh(bm)
    bm.created_date = to_seoul(bm.created_date)
    return bm


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
    # 리스트 반환 시 각 북마크의 created_date 변환
    for bm in bookmarks:
        bm.created_date = to_seoul(bm.created_date)
    return bookmarks
