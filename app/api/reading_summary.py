from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.auth import get_current_user
from app.database import get_db
from app.models import Book, BookReadingSummary, User
from app.schemas.reading_summary import ReadingSummaryContent, ReadingSummaryDeleteResponse, ReadingSummaryGenerateResponse, ReadingSummaryResponse, ReadingSummaryStats
from app.services.reading_summary import build_summary_text, collect_summary_inputs, delete_summary_data, enqueue_summary_job, get_or_create_summary, is_auto_eligible, mark_summary_dirty

router = APIRouter(tags=["reading-summary"])


def _ensure_book_exists(db: Session, book_id: int) -> None:
    if not db.query(Book.id).filter(Book.id == book_id).first():
        raise HTTPException(status_code=404, detail="책을 찾을 수 없습니다")


def _serialize(summary: BookReadingSummary, stats: dict) -> ReadingSummaryResponse:
    summary_json = summary.summary_json or {}
    return ReadingSummaryResponse(
        bookId=summary.book_id,
        status=summary.status.value if hasattr(summary.status, 'value') else str(summary.status),
        summaryDirty=bool(summary.summary_dirty),
        autoEligible=is_auto_eligible(stats),
        stats=ReadingSummaryStats(**stats),
        summaryText=build_summary_text(stats),
        summaryContent=ReadingSummaryContent(
            summary=summary_json.get('summary'),
            keyPoints=summary_json.get('keyPoints') or [],
            notesDigest=summary_json.get('notesDigest') or [],
        ),
        lastSourceUpdatedAt=summary.last_source_updated_at,
        lastSummarizedAt=summary.last_summarized_at,
        errorMessage=summary.error_message,
    )


@router.get('/books/{book_id}/reading-summary', response_model=ReadingSummaryResponse, summary='책별 AI 독서 요약 조회')
def get_reading_summary(
    book_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _ensure_book_exists(db, book_id)
    summary = get_or_create_summary(db, current_user.id, book_id)
    payload = collect_summary_inputs(db, current_user.id, book_id)
    if summary.stats_json != payload['stats']:
        summary.stats_json = payload['stats']
        db.commit()
        db.refresh(summary)
    return _serialize(summary, payload['stats'])


@router.post('/books/{book_id}/reading-summary/generate', response_model=ReadingSummaryGenerateResponse, summary='책별 AI 독서 요약 생성 요청')
def generate_reading_summary(
    book_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _ensure_book_exists(db, book_id)
    mark_summary_dirty(db, current_user.id, book_id)
    summary, queued, reason = enqueue_summary_job(db, current_user.id, book_id, trigger='manual')
    stats = summary.stats_json or {}
    return ReadingSummaryGenerateResponse(
        bookId=book_id,
        status=summary.status.value if hasattr(summary.status, 'value') else str(summary.status),
        summaryDirty=bool(summary.summary_dirty),
        autoEligible=is_auto_eligible(stats),
        queued=queued,
        reason=reason,
    )


@router.delete('/books/{book_id}/reading-summary', response_model=ReadingSummaryDeleteResponse, summary='책별 AI 독서 요약 삭제')
def delete_reading_summary(
    book_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _ensure_book_exists(db, book_id)
    deleted, deleted_jobs, deleted_notifications = delete_summary_data(db, current_user.id, book_id)
    return ReadingSummaryDeleteResponse(
        bookId=book_id,
        deleted=deleted,
        deletedJobs=deleted_jobs,
        deletedNotifications=deleted_notifications,
    )
