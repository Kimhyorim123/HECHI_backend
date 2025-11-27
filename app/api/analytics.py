from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from pydantic import BaseModel, Field

from app.core.auth import get_current_user
from app.database import get_db
from app.models import User, SearchHistory, BookView, Book

router = APIRouter(prefix="/analytics", tags=["analytics"])


class SearchLogRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=255)


class ViewLogRequest(BaseModel):
    book_id: int


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
