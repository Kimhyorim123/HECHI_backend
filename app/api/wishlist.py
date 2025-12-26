from fastapi import APIRouter, Depends, HTTPException, Query
from datetime import datetime
from app.core.utils import to_seoul
from sqlalchemy.orm import Session

from app.core.auth import get_current_user, get_db
from app.models import Wishlist, Book, UserBook
from fastapi.responses import JSONResponse

router = APIRouter(prefix="/wishlist", tags=["wishlist"]) 

@router.post("/", status_code=201, summary="위시리스트 추가 (book_id 또는 user_book_id 지원)")
def add_to_wishlist(
    book_id: int | None = Query(None),
    user_book_id: int | None = Query(None),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    # 입력 검증: 둘 중 정확히 하나만 허용
    if (book_id is None and user_book_id is None) or (book_id is not None and user_book_id is not None):
        raise HTTPException(status_code=422, detail="Provide exactly one of book_id or user_book_id")

    if user_book_id is not None:
        ub = db.query(UserBook).filter(UserBook.id == user_book_id, UserBook.user_id == current_user.id).first()
        if not ub:
            raise HTTPException(status_code=404, detail="UserBook not found")
        book_id = ub.book_id
    # 책 존재 여부 확인(선택적): 없으면 404
    book = db.query(Book).filter(Book.id == book_id).first()
    if not book:
        raise HTTPException(status_code=404, detail="Book not found")

    exists = db.query(Wishlist).filter(Wishlist.user_id == current_user.id, Wishlist.book_id == book_id).first()
    if exists:
        # 이미 존재하면 200 OK로 무해하게 처리하고 user_book_id 반환
        ub = (
            db.query(UserBook)
            .filter(UserBook.user_id == current_user.id, UserBook.book_id == book_id)
            .first()
        )
        if not ub:
            ub = UserBook(user_id=current_user.id, book_id=book_id)
            db.add(ub)
            db.commit()
            db.refresh(ub)
        return JSONResponse({"ok": True, "book_id": book_id, "user_book_id": ub.id, "already": True}, status_code=200)

    # 사용자의 서재 레코드 확보
    ub = (
        db.query(UserBook)
        .filter(UserBook.user_id == current_user.id, UserBook.book_id == book_id)
        .first()
    )
    if not ub:
        ub = UserBook(user_id=current_user.id, book_id=book_id)
        db.add(ub)
        db.flush()

    # created_at, wishlist_at 모두 명시적으로 설정
    now = datetime.utcnow()
    w = Wishlist(user_id=current_user.id, book_id=book_id, created_at=now, wishlist_at=now)
    db.add(w)
    db.commit()
    db.refresh(w)
    return {"ok": True, "book_id": book_id, "user_book_id": ub.id, "added_at": to_seoul(w.created_at)}

@router.get("/", summary="내 위시리스트 조회")
def list_wishlist(
    limit: int = 50,
    offset: int = 0,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    rows = (
        db.query(Wishlist, UserBook)
        .join(UserBook, (UserBook.user_id == Wishlist.user_id) & (UserBook.book_id == Wishlist.book_id))
        .filter(Wishlist.user_id == current_user.id)
        .order_by(Wishlist.id.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )
    out = []
    for w, ub in rows:
        out.append({
            "user_book_id": ub.id,
            "book_id": w.book_id,
            "added_at": to_seoul(w.created_at) if w.created_at else None,
        })
    return out

@router.delete("/{book_id}")
def remove_from_wishlist(book_id: int, db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    exists = db.query(Wishlist).filter(Wishlist.user_id == current_user.id, Wishlist.book_id == book_id).first()
    if not exists:
        # 없으면 404 반환
        raise HTTPException(status_code=404, detail="Not in wishlist")

    db.delete(exists)
    db.commit()
    # user_book_id 반환(있을 경우)
    ub = (
        db.query(UserBook)
        .filter(UserBook.user_id == current_user.id, UserBook.book_id == book_id)
        .first()
    )
    return {"ok": True, "book_id": book_id, "user_book_id": ub.id if ub else None}
