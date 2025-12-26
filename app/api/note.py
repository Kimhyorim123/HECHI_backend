from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.auth import get_current_user
from app.database import get_db
from app.models import Note, User, UserBook
from app.schemas.note import NoteCreateRequest, NoteUpdateRequest, NoteResponse
from app.core.utils import to_seoul

router = APIRouter(prefix="/notes", tags=["notes"])


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


@router.post("/", response_model=NoteResponse)
def create_note(
    payload: NoteCreateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    ub = _get_or_create_user_book(db, current_user.id, payload.book_id)
    note = Note(user_book_id=ub.id, content=payload.content)
    db.add(note)
    db.commit()
    db.refresh(note)
    note.created_date = to_seoul(note.created_date)
    return note


@router.put("/{note_id}", response_model=NoteResponse)
def update_note(
    note_id: int,
    payload: NoteUpdateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    note = (
        db.query(Note)
        .join(UserBook, UserBook.id == Note.user_book_id)
        .filter(Note.id == note_id, UserBook.user_id == current_user.id)
        .first()
    )
    if not note:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="노트를 찾을 수 없습니다")

    note.content = payload.content
    db.commit()
    db.refresh(note)
    note.created_date = to_seoul(note.created_date)
    return note


@router.delete("/{note_id}", status_code=204)
def delete_note(
    note_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    note = (
        db.query(Note)
        .join(UserBook, UserBook.id == Note.user_book_id)
        .filter(Note.id == note_id, UserBook.user_id == current_user.id)
        .first()
    )
    if not note:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="노트를 찾을 수 없습니다")

    db.delete(note)
    db.commit()
    return None


@router.get("/books/{book_id}", response_model=list[NoteResponse])
def list_notes_for_book(
    book_id: int,
    limit: int = 50,
    offset: int = 0,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    notes = (
        db.query(Note)
        .join(UserBook, UserBook.id == Note.user_book_id)
        .filter(UserBook.user_id == current_user.id, UserBook.book_id == book_id)
        .order_by(Note.created_date.desc(), Note.id.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )
    for n in notes:
        n.created_date = to_seoul(n.created_date)
    return notes
