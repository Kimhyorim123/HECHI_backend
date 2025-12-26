from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.auth import get_current_user
from app.database import get_db
from app.models import Highlight, User, UserBook, Book, Author, BookAuthor
from app.schemas.highlight import (
    HighlightCreateRequest,
    HighlightUpdateRequest,
    HighlightResponse,
)

router = APIRouter(prefix="/highlights", tags=["highlights"])


# ✅ Swagger 응답을 "string"이 아니라 원하는 JSON 스키마로 보이게 하려면 response_model 필요
# (원하는 응답: book_id, title, author, sentence)
class RandomPublicHighlightResponseSchema:
    # Pydantic BaseModel을 직접 import해서 쓰는 게 정석이지만,
    # "전체 코드" 요청이므로 여기서는 한 파일에 다 넣는 형태로 작성.
    # 실제 프로젝트에서는 app/schemas/highlight.py로 옮기는 걸 권장.
    pass


# ---- Pydantic 스키마를 파일 내에 포함시키는 버전 ----
from pydantic import BaseModel


class RandomPublicHighlightResponse(BaseModel):
    book_id: int
    title: str
    author: Optional[str] = None
    sentence: str


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
        memo=payload.memo,
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
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="하이라이트를 찾을 수 없습니다"
        )

    if payload.sentence is not None:
        hl.sentence = payload.sentence
    if payload.is_public is not None:
        hl.is_public = payload.is_public

    # 메모는 명시적으로 null로 설정할 수도 있음
    # (exclude_unset=True에서 memo가 존재하지만 값이 None인 경우도 반영)
    if "memo" in payload.model_dump(exclude_unset=True):
        hl.memo = payload.memo

    if payload.page is not None:
        hl.page = payload.page

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
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="하이라이트를 찾을 수 없습니다"
        )

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


@router.get(
    "/random-public",
    summary="공개 하이라이트 랜덤 제공",
    response_model=RandomPublicHighlightResponse,
)
def get_random_public_highlight(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    # 내 user_book_id 목록(내가 만든 하이라이트는 제외)
    my_userbook_ids_subq = db.query(UserBook.id).filter(UserBook.user_id == current_user.id)

    # ✅ Highlight -> UserBook -> Book -> (BookAuthor -> Author) 를 조인 1방으로
    row = (
        db.query(
            Book.id.label("book_id"),
            Book.title.label("title"),
            Author.name.label("author"),
            Highlight.sentence.label("sentence"),
        )
        .join(UserBook, UserBook.id == Highlight.user_book_id)
        .join(Book, Book.id == UserBook.book_id)
        .outerjoin(BookAuthor, BookAuthor.book_id == Book.id)
        .outerjoin(Author, Author.id == BookAuthor.author_id)
        .filter(Highlight.is_public == True)
        .filter(~Highlight.user_book_id.in_(my_userbook_ids_subq))
        .order_by(func.rand())
        .limit(1)
        .first()
    )

    if not row:
        raise HTTPException(status_code=404, detail="공개 하이라이트가 없습니다.")

    return {
        "book_id": row.book_id,
        "title": row.title,
        "author": row.author,
        "sentence": row.sentence,
    }
