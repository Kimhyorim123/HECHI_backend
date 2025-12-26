from datetime import datetime
from typing import List, Optional

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Query,
    status,
)
from sqlalchemy.orm import Session
from pydantic import BaseModel, Field

from app.core.auth import get_current_user
from app.database import get_db
from app.models import (
    ReadingSession,
    ReadingEvent,
    ReadingEventType,
    User,
    Book,
)
from app.schemas.reading import (
    ReadingSessionStartRequest,
    ReadingEventCreateRequest,
    ReadingSessionEndRequest,
    ReadingSessionResponse,
    ReadingEventResponse,
)

router = APIRouter(prefix="/reading", tags=["reading"])


# ---------------------------------
# Pydantic 응답 모델 (Swagger 스키마용)
# ---------------------------------
class ReadingSummaryResponse(BaseModel):
    book_id: int = Field(..., example=123)
    total_session_seconds: int = Field(..., example=5400)
    progress_percent: Optional[float] = Field(
        None,
        example=85.0,
        description="(최대 읽은 페이지 / 전체 페이지) * 100",
    )
    sessions_count: int = Field(..., example=12)
    last_read_at: Optional[datetime] = Field(
        None,
        example="2025-12-22T12:34:56",
        description="가장 마지막으로 읽은 시간",
    )
    max_end_page: int = Field(..., example=300)
    start_page: int = Field(..., example=1)
    total_pages: Optional[int] = Field(
        None,
        example=350,
        description="책 전체 페이지 수 (알 수 없으면 null)",
    )


class UserReadingSummaryResponse(BaseModel):
    user_id: int = Field(..., example=1)
    total_reading_seconds: int = Field(..., example=123456)
    books_count: int = Field(
        ...,
        example=27,
        description="지금까지 읽기 기록이 있는 서로 다른 책 개수",
    )
    first_read_at: Optional[datetime] = Field(
        None,
        example="2024-01-01T10:00:00",
        description="가장 처음 읽기 시작한 시각",
    )
    last_read_at: Optional[datetime] = Field(
        None,
        example="2025-12-22T12:34:56",
        description="가장 마지막으로 읽은 시각",
    )


# -------------------------------
# 내부용: 최근 페이지 계산 함수
# -------------------------------
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
        .filter(
            ReadingSession.user_id == user_id,
            ReadingSession.book_id == book_id,
        )
        .order_by(ReadingSession.id.desc())
        .first()
    )
    if last_session and last_session.end_page is not None:
        return int(last_session.end_page)

    return None


# -------------------------------
# 세션 시작
# -------------------------------
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


# -------------------------------
# 이벤트 추가
# -------------------------------
@router.post(
    "/sessions/{session_id}/events",
    response_model=ReadingEventResponse,
    summary="읽기 이벤트 추가",
)
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
        raise HTTPException(status_code=404, detail="세션을 찾을 수 없습니다")

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
                session.total_seconds = int(
                    (session.end_time - session.start_time).total_seconds()
                )
            except Exception:
                pass

    db.commit()
    db.refresh(event)
    db.refresh(session)
    return event


# -------------------------------
# 세션 종료
# -------------------------------
@router.post(
    "/sessions/{session_id}/end",
    response_model=ReadingSessionResponse,
    summary="세션 종료",
)
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
        raise HTTPException(status_code=404, detail="세션을 찾을 수 없습니다")

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

    db.commit()
    db.refresh(session)
    return session


# -------------------------------
# 세션 목록 (book_id 필터링 가능)
# -------------------------------
@router.get(
    "/sessions",
    response_model=List[ReadingSessionResponse],
    summary="세션 목록 조회",
)
def list_sessions(
    book_id: Optional[int] = Query(
        None,
        description="특정 책 ID로 필터링 (옵션)",
    ),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    query = db.query(ReadingSession).filter(
        ReadingSession.user_id == current_user.id,
    )

    if book_id is not None:
        query = query.filter(ReadingSession.book_id == book_id)

    return query.order_by(ReadingSession.id.desc()).all()


# -------------------------------
# 단일 세션 조회
# -------------------------------
@router.get(
    "/sessions/{session_id}",
    response_model=ReadingSessionResponse,
    summary="단일 세션 조회",
)
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
        raise HTTPException(status_code=404, detail="세션을 찾을 수 없습니다")
    return session


# -------------------------------
# 특정 책 요약
# -------------------------------
@router.get(
    "/summary",
    response_model=ReadingSummaryResponse,
    summary="책별 읽기 요약",
)
def get_reading_summary(
    book_id: int = Query(..., description="책 ID"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    sessions = db.query(ReadingSession).filter(
        ReadingSession.user_id == current_user.id,
        ReadingSession.book_id == book_id,
    ).all()

    total_session_seconds = sum(s.total_seconds or 0 for s in sessions)
    sessions_count = len(sessions)

    last_read_at = max(
        [s.end_time for s in sessions if s.end_time],
        default=None,
    )

    max_end_page = max(
        [s.end_page or 0 for s in sessions],
        default=0,
    )

    min_start_page = min(
        [s.start_page or 1 for s in sessions],
        default=1,
    )

    book = db.query(Book).filter(Book.id == book_id).first()
    total_pages = book.total_pages if book else None

    progress_percent: Optional[float] = None
    if total_pages and max_end_page:
        progress_percent = round((max_end_page / total_pages) * 100, 2)

    return ReadingSummaryResponse(
        book_id=book_id,
        total_session_seconds=total_session_seconds,
        progress_percent=progress_percent,
        sessions_count=sessions_count,
        last_read_at=last_read_at,
        max_end_page=max_end_page,
        start_page=min_start_page,
        total_pages=total_pages,
    )


# -------------------------------
# 사용자 전체 요약
# -------------------------------
@router.get(
    "/summary/user",
    response_model=UserReadingSummaryResponse,
    summary="사용자 전체 읽기 요약",
)
def get_user_reading_summary(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    sessions = db.query(ReadingSession).filter(
        ReadingSession.user_id == current_user.id,
    ).all()

    total_reading_seconds = sum(s.total_seconds or 0 for s in sessions)

    books_count = (
        db.query(ReadingSession.book_id)
        .filter(ReadingSession.user_id == current_user.id)
        .distinct()
        .count()
    )

    first_read_at = min(
        [s.start_time for s in sessions if s.start_time],
        default=None,
    )
    last_read_at = max(
        [s.end_time for s in sessions if s.end_time],
        default=None,
    )

    return UserReadingSummaryResponse(
        user_id=current_user.id,
        total_reading_seconds=total_reading_seconds,
        books_count=books_count,
        first_read_at=first_read_at,
        last_read_at=last_read_at,
    )
