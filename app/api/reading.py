@router.get("/summary/user", tags=["reading"])
def get_user_reading_summary(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    # 전체 세션
    sessions = db.query(ReadingSession).filter(
        ReadingSession.user_id == current_user.id
    ).all()
    total_reading_seconds = sum(s.total_seconds or 0 for s in sessions)
    # 읽은 책 개수
    books_count = db.query(ReadingSession.book_id).filter(
        ReadingSession.user_id == current_user.id
    ).distinct().count()
    # 첫/마지막 독서 시각
    first_read_at = min([s.start_time for s in sessions if s.start_time], default=None)
    last_read_at = max([s.end_time for s in sessions if s.end_time], default=None)
    return {
        "user_id": current_user.id,
        "total_reading_seconds": total_reading_seconds,
        "books_count": books_count,
        "first_read_at": first_read_at.isoformat() if first_read_at else None,
        "last_read_at": last_read_at.isoformat() if last_read_at else None,
    }
from fastapi import APIRouter
from fastapi import Query
from app.models import Book

router = APIRouter()

@router.get("/summary", tags=["reading"])
def get_reading_summary(
    book_id: int = Query(..., description="책 ID"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    # 해당 책의 모든 세션 조회
    sessions = db.query(ReadingSession).filter(
        ReadingSession.user_id == current_user.id,
        ReadingSession.book_id == book_id
    ).all()
    total_session_seconds = sum(s.total_seconds or 0 for s in sessions)
    sessions_count = len(sessions)
    last_read_at = max([s.end_time for s in sessions if s.end_time], default=None)
    # 최대 읽은 페이지(완독률 계산용)
    max_end_page = max([s.end_page or 0 for s in sessions], default=0)
    min_start_page = min([s.start_page or 1 for s in sessions], default=1)
    # 책 전체 페이지
    book = db.query(Book).filter(Book.id == book_id).first()
    total_pages = book.total_pages if book else None
    progress_percent = None
    if total_pages and max_end_page:
        progress_percent = round((max_end_page / total_pages) * 100, 2)
    return {
        "book_id": book_id,
        "total_session_seconds": total_session_seconds,
        "progress_percent": progress_percent,
        "sessions_count": sessions_count,
        "last_read_at": last_read_at.isoformat() if last_read_at else None,
        "max_end_page": max_end_page,
        "start_page": min_start_page,
        "total_pages": total_pages,
    }
from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.auth import get_current_user
from app.database import get_db
from app.models import ReadingSession, ReadingEvent, ReadingEventType, User
from app.schemas.reading import (
    ReadingSessionStartRequest,
    ReadingEventCreateRequest,
    ReadingSessionEndRequest,
    ReadingSessionResponse,
    ReadingEventResponse,
)

router = APIRouter(prefix="/reading", tags=["reading"])


def _get_last_page_read(db: Session, user_id: int, book_id: int) -> Optional[int]:
    last_event_page = (
        db.query(ReadingEvent.page)
        .join(ReadingSession, ReadingEvent.session_id == ReadingSession.id)
        .filter(
            ReadingSession.user_id == user_id,
            ReadingSession.book_id == book_id,
            ReadingEvent.page.isnot(None),
        )
        .order_by(ReadingEvent.occurred_at.desc(), ReadingEvent.id.desc())
        .limit(1)
        .scalar()
    )
    if last_event_page is not None:
        return int(last_event_page)

    last_session = (
        db.query(ReadingSession)
        .filter(ReadingSession.user_id == user_id, ReadingSession.book_id == book_id)
        .order_by(ReadingSession.id.desc())
        .first()
    )
    if last_session and last_session.end_page is not None:
        return int(last_session.end_page)

    return None


@router.post(
    "/sessions",
    response_model=ReadingSessionResponse,
    summary="읽기 세션 시작",
    description="start_page를 주지 않으면 서버가 최근 읽은 페이지(최근 이벤트→최근 세션 end_page→없으면 1)로 자동 설정합니다.",
)
def start_session(
    payload: ReadingSessionStartRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    inferred_start_page = payload.start_page
    if inferred_start_page is None:
        inferred_start_page = _get_last_page_read(db, current_user.id, payload.book_id)
        if inferred_start_page is None:
            inferred_start_page = 1

    session = ReadingSession(
        user_id=current_user.id,
        book_id=payload.book_id,
        start_page=inferred_start_page,
    )
    db.add(session)
    db.flush()

    start_event = ReadingEvent(
        session_id=session.id,
        event_type=ReadingEventType.START,
        page=inferred_start_page,
    )
    db.add(start_event)
    db.commit()
    db.refresh(session)

    return session


@router.post("/sessions/{session_id}/events", response_model=ReadingEventResponse)
def add_event(
    session_id: int,
    payload: ReadingEventCreateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    session = db.query(ReadingSession).filter(
        ReadingSession.id == session_id,
        ReadingSession.user_id == current_user.id,
    ).first()
    if not session:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="세션을 찾을 수 없습니다")

    try:
        event_type = ReadingEventType(payload.event_type)
    except ValueError:
        raise HTTPException(status_code=400, detail="유효하지 않은 이벤트 타입")

    occurred = payload.occurred_at or datetime.utcnow()

    event = ReadingEvent(
        session_id=session.id,
        event_type=event_type,
        page=payload.page,
        occurred_at=occurred,
    )
    db.add(event)

    if event_type == ReadingEventType.END:
        if session.end_time is None:
            session.end_time = occurred
        if payload.page is not None:
            session.end_page = payload.page
        if session.start_time and session.end_time and not session.total_seconds:
            try:
                session.total_seconds = int((session.end_time - session.start_time).total_seconds())
            except Exception:
                pass

    db.commit()
    db.refresh(event)
    db.refresh(session)

    event.occurred_at = to_seoul(event.occurred_at)
    return event


@router.post("/sessions/{session_id}/end", response_model=ReadingSessionResponse)
def end_session(
    session_id: int,
    payload: ReadingSessionEndRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    session = db.query(ReadingSession).filter(
        ReadingSession.id == session_id,
        ReadingSession.user_id == current_user.id,
    ).first()
    if not session:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="세션을 찾을 수 없습니다")

    if session.end_time is not None:
        raise HTTPException(status_code=400, detail="이미 종료된 세션입니다")

    now = datetime.utcnow()
    session.end_time = now
    session.end_page = payload.end_page
    session.total_seconds = payload.total_seconds

    end_event = ReadingEvent(
        session_id=session.id,
        event_type=ReadingEventType.END,
        page=payload.end_page,
        occurred_at=now,
    )
    db.add(end_event)

    # === UserPage upsert ===
    from app.models import UserBook, UserPage
    # UserBook 찾기
    user_book = db.query(UserBook).filter(
        UserBook.user_id == current_user.id,
        UserBook.book_id == session.book_id
    ).first()
    if user_book:
        # 날짜는 KST 기준으로 변환
        from app.core.utils import to_seoul
        kst_end_time = to_seoul(session.end_time)
        reading_date = kst_end_time.date()
        user_page = db.query(UserPage).filter(
            UserPage.user_book_id == user_book.id,
            UserPage.reading_date == reading_date
        ).first()
        if user_page:
            # end_page, reading_seconds 갱신(더 큰 값으로)
            user_page.end_page = max(user_page.end_page or 0, session.end_page or 0)
            user_page.reading_seconds = (user_page.reading_seconds or 0) + (session.total_seconds or 0)
        else:
            user_page = UserPage(
                user_book_id=user_book.id,
                reading_date=reading_date,
                start_page=session.start_page or 1,
                end_page=session.end_page or session.start_page or 1,
                reading_seconds=session.total_seconds or 0,
            )
            db.add(user_page)

    db.commit()
    db.refresh(session)

    session.end_time = to_seoul(session.end_time)
    return session


@router.get("/sessions", response_model=List[ReadingSessionResponse])
def list_sessions(
    book_id: int = Query(None, description="특정 책의 세션만 조회"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    query = db.query(ReadingSession).filter(ReadingSession.user_id == current_user.id)
    if book_id is not None:
        query = query.filter(ReadingSession.book_id == book_id)
    sessions = query.order_by(ReadingSession.id.desc()).all()
    for s in sessions:
        s.start_time = to_seoul(s.start_time)
        if s.end_time:
            s.end_time = to_seoul(s.end_time)
        # events의 occurred_at도 변환
        if hasattr(s, "events") and s.events:
            for e in s.events:
                e.occurred_at = to_seoul(e.occurred_at)
    return sessions


@router.get("/sessions/{session_id}", response_model=ReadingSessionResponse)
def get_session(
    session_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    session = db.query(ReadingSession).filter(
        ReadingSession.id == session_id,
        ReadingSession.user_id == current_user.id,
    ).first()
    if not session:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="세션을 찾을 수 없습니다")
    session.start_time = to_seoul(session.start_time)
    if session.end_time:
        session.end_time = to_seoul(session.end_time)
    return session
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
)
@router.post("/sessions", response_model=ReadingSessionResponse, summary="읽기 세션 시작", description="start_page를 주지 않으면 서버가 최근 읽은 페이지(최근 이벤트→최근 세션 end_page→없으면 1)로 자동 설정합니다.")
def start_session(
    payload: ReadingSessionStartRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    # 기존 진행중인 세션(종료 X)이 있으면 종료를 요구할 수 있으나, 우선 중복 생성 허용
    # 클라이언트가 start_page를 주지 않으면 서버가 마지막 읽은 페이지를 기준으로 설정
    inferred_start_page = payload.start_page
    if inferred_start_page is None:
        inferred_start_page = _get_last_page_read(db, current_user.id, payload.book_id)
        if inferred_start_page is None:
            inferred_start_page = 1  # 기본값

    session = ReadingSession(
        user_id=current_user.id,
        book_id=payload.book_id,
        start_page=inferred_start_page,
    )
    db.add(session)
    db.flush()  # session.id 확보

    # START 이벤트 기록
    start_event = ReadingEvent(
        session_id=session.id,
        event_type=ReadingEventType.START,
        page=inferred_start_page,
    )
    db.add(start_event)
    db.commit()
    db.refresh(session)

    return session


@router.post("/sessions/{session_id}/events", response_model=ReadingEventResponse)
def add_event(
    session_id: int,
    payload: ReadingEventCreateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    session = db.query(ReadingSession).filter(
        ReadingSession.id == session_id,
        ReadingSession.user_id == current_user.id,
    ).first()
    if not session:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="세션을 찾을 수 없습니다")

    try:
        event_type = ReadingEventType(payload.event_type)
    except ValueError:
        raise HTTPException(status_code=400, detail="유효하지 않은 이벤트 타입")

    occurred = payload.occurred_at or datetime.utcnow()

    event = ReadingEvent(
        session_id=session.id,
        event_type=event_type,
        page=payload.page,
        occurred_at=occurred,
    )
    db.add(event)

    # If END event is sent via /events, also close the session for convenience
    if event_type == ReadingEventType.END:
        # Only set if not already ended
        if session.end_time is None:
            session.end_time = occurred
        if payload.page is not None:
            session.end_page = payload.page
        # total_seconds best-effort: if start_time exists, compute diff
        if session.start_time and session.end_time and not session.total_seconds:
            try:
                session.total_seconds = int((session.end_time - session.start_time).total_seconds())
            except Exception:
                pass

    db.commit()
    # Ensure both event and session reflect latest state
    db.refresh(event)
    db.refresh(session)

    return event


@router.post("/sessions/{session_id}/end", response_model=ReadingSessionResponse)
def end_session(
    session_id: int,
    payload: ReadingSessionEndRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    session = db.query(ReadingSession).filter(
        ReadingSession.id == session_id,
        ReadingSession.user_id == current_user.id,
    ).first()
    if not session:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="세션을 찾을 수 없습니다")

    if session.end_time is not None:
        raise HTTPException(status_code=400, detail="이미 종료된 세션입니다")

    now = datetime.utcnow()
    session.end_time = now
    session.end_page = payload.end_page
    session.total_seconds = payload.total_seconds

    # END 이벤트 기록
    end_event = ReadingEvent(
        session_id=session.id,
        event_type=ReadingEventType.END,
        page=payload.end_page,
        occurred_at=now,
    )
    db.add(end_event)
    db.commit()
    db.refresh(session)

    return session


@router.get("/sessions", response_model=List[ReadingSessionResponse])
def list_sessions(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    sessions = (
        db.query(ReadingSession)
        .filter(ReadingSession.user_id == current_user.id)
        .order_by(ReadingSession.id.desc())
        .all()
    )
    return sessions


@router.get("/sessions/{session_id}", response_model=ReadingSessionResponse)
def get_session(
    session_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    session = db.query(ReadingSession).filter(
        ReadingSession.id == session_id,
        ReadingSession.user_id == current_user.id,
    ).first()
    if not session:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="세션을 찾을 수 없습니다")
    return session
