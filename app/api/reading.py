from datetime import datetime
from typing import List

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


@router.post("/sessions", response_model=ReadingSessionResponse)
def start_session(
    payload: ReadingSessionStartRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    # 기존 진행중인 세션(종료 X)이 있으면 종료를 요구할 수 있으나, 우선 중복 생성 허용
    session = ReadingSession(
        user_id=current_user.id,
        book_id=payload.book_id,
        start_page=payload.start_page,
    )
    db.add(session)
    db.flush()  # session.id 확보

    # START 이벤트 기록
    start_event = ReadingEvent(
        session_id=session.id,
        event_type=ReadingEventType.START,
        page=payload.start_page,
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

    event = ReadingEvent(
        session_id=session.id,
        event_type=event_type,
        page=payload.page,
        occurred_at=payload.occurred_at or datetime.utcnow(),
    )
    db.add(event)
    db.commit()
    db.refresh(event)

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
