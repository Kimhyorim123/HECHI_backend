from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.core.auth import get_current_user
from app.database import get_db
from app.models import User, UserBook, Book, ReadingSession, Bookmark, Highlight, Note
from pydantic import BaseModel

router = APIRouter(prefix="/reading-status", tags=["reading-status"])


class StatusUpdate(BaseModel):
    book_id: int
    status: str  # e.g., READING, COMPLETED, PENDING, ARCHIVED


@router.post("/update")
def update_status(payload: StatusUpdate, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    ub = db.query(UserBook).filter_by(user_id=user.id, book_id=payload.book_id).first()
    if not ub:
        ub = UserBook(user_id=user.id, book_id=payload.book_id)
        db.add(ub)
        db.flush()
    ub.status = payload.status
    db.commit()
    return {"ok": True}


@router.get("/summary/{book_id}")
def summary(book_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    book = db.get(Book, book_id)
    if not book:
        raise HTTPException(status_code=404, detail="Book not found")

    # 진행률
    last_session = (
        db.query(ReadingSession)
        .filter(ReadingSession.user_id == user.id, ReadingSession.book_id == book_id)
        .order_by(ReadingSession.id.desc())
        .first()
    )
    end_page = last_session.end_page or 0 if last_session else 0
    total_pages = book.total_pages or 0
    progress = float(end_page) / total_pages if total_pages else 0.0

    # 기간(첫 시작 ~ 마지막 종료)
    first_start = (
        db.query(func.min(ReadingSession.start_time))
        .filter(ReadingSession.user_id == user.id, ReadingSession.book_id == book_id)
        .scalar()
    )
    last_end = (
        db.query(func.max(ReadingSession.end_time))
        .filter(ReadingSession.user_id == user.id, ReadingSession.book_id == book_id)
        .scalar()
    )

    # 총 시간(세션들의 total_seconds 합산; 없으면 0)
    total_seconds = (
        db.query(func.coalesce(func.sum(ReadingSession.total_seconds), 0))
        .filter(ReadingSession.user_id == user.id, ReadingSession.book_id == book_id)
        .scalar()
        or 0
    )

    # 활동 개수
    bookmark_count = (
        db.query(func.count(Bookmark.id))
        .join(UserBook, UserBook.id == Bookmark.user_book_id)
        .filter(UserBook.user_id == user.id, UserBook.book_id == book_id)
        .scalar()
        or 0
    )
    highlight_count = (
        db.query(func.count(Highlight.id))
        .join(UserBook, UserBook.id == Highlight.user_book_id)
        .filter(UserBook.user_id == user.id, UserBook.book_id == book_id)
        .scalar()
        or 0
    )
    note_count = (
        db.query(func.count(Note.id))
        .join(UserBook, UserBook.id == Note.user_book_id)
        .filter(UserBook.user_id == user.id, UserBook.book_id == book_id)
        .scalar()
        or 0
    )

    return {
        "progress": round(progress, 4),
        "period": {
            "start": first_start.isoformat() if first_start else None,
            "end": last_end.isoformat() if last_end else None,
        },
        "total_time_seconds": int(total_seconds),
        "activity": {
            "bookmarks": int(bookmark_count),
            "highlights": int(highlight_count),
            "notes": int(note_count),
        },
    }
