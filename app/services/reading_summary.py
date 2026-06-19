from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import and_, func, or_
from sqlalchemy.orm import Session

from app.models import AIJob, AIJobStatus, AIJobType, Author, Book, BookAuthor, BookReadingSummary, Bookmark, Highlight, Note, NotificationType, ReadingSession, ReadingSummaryStatus, UserBook
from app.schemas.reading_summary import ReadingSummaryPayload
from app.services.notify import create_notification

AUTO_MIN_NOTE_COUNT = 3
AUTO_MIN_NOTE_CHARACTERS = 500
AUTO_DEBOUNCE_MINUTES = 5
SUMMARY_TARGET_TYPE = "BOOK_READING_SUMMARY"


def utcnow() -> datetime:
    return datetime.utcnow()


def _default_stats() -> dict[str, Any]:
    return {
        "noteCount": 0,
        "noteCharacterCount": 0,
        "highlightCount": 0,
        "bookmarkCount": 0,
        "totalReadingSeconds": 0,
        "startPage": None,
        "endPage": None,
    }


def _default_summary_content() -> dict[str, Any]:
    return {
        "summary": None,
        "keyPoints": [],
        "notesDigest": [],
    }


def _humanize_duration(total_seconds: int) -> str:
    if total_seconds <= 0:
        return "0분"
    hours = total_seconds // 3600
    minutes = (total_seconds % 3600) // 60
    if hours and minutes:
        return f"{hours}시간 {minutes}분"
    if hours:
        return f"{hours}시간"
    return f"{minutes}분"


def build_summary_text(stats: dict[str, Any]) -> list[str]:
    lines = [
        f"이 책에는 총 {stats['noteCount']}개의 메모를 남기셨어요.",
        f"총 {stats['noteCharacterCount']}자의 기록이 쌓였어요.",
        f"하이라이트는 {stats['highlightCount']}개, 북마크는 {stats['bookmarkCount']}개 남기셨어요.",
    ]
    if stats.get('startPage') is not None and stats.get('endPage') is not None:
        lines.append(f"{stats['startPage']}페이지부터 {stats['endPage']}페이지까지 읽은 흔적이 있어요.")
    if stats.get('totalReadingSeconds', 0) > 0:
        lines.append(f"총 {_humanize_duration(int(stats['totalReadingSeconds']))} 동안 읽으셨어요.")
    return lines


def get_or_create_summary(db: Session, user_id: int, book_id: int) -> BookReadingSummary:
    summary = db.query(BookReadingSummary).filter(BookReadingSummary.user_id == user_id, BookReadingSummary.book_id == book_id).first()
    if summary:
        return summary
    summary = BookReadingSummary(
        user_id=user_id,
        book_id=book_id,
        status=ReadingSummaryStatus.NOT_READY,
        summary_dirty=False,
        stats_json=_default_stats(),
        summary_json=_default_summary_content(),
    )
    db.add(summary)
    db.commit()
    db.refresh(summary)
    return summary


def collect_summary_inputs(db: Session, user_id: int, book_id: int) -> dict[str, Any]:
    stats = _default_stats()
    user_book = db.query(UserBook).filter(UserBook.user_id == user_id, UserBook.book_id == book_id).first()

    note_rows = []
    highlight_rows = []
    bookmark_rows = []
    if user_book:
        note_rows = db.query(Note).filter(Note.user_book_id == user_book.id).order_by(Note.created_date.asc(), Note.id.asc()).all()
        highlight_rows = db.query(Highlight).filter(Highlight.user_book_id == user_book.id).order_by(Highlight.created_date.asc(), Highlight.id.asc()).all()
        bookmark_rows = db.query(Bookmark).filter(Bookmark.user_book_id == user_book.id).order_by(Bookmark.created_date.asc(), Bookmark.id.asc()).all()

    notes = [n.content.strip() for n in note_rows if (n.content or '').strip()]
    highlights = []
    for h in highlight_rows:
        sentence = (h.sentence or '').strip()
        memo = (h.memo or '').strip()
        if sentence and memo:
            highlights.append(f"{sentence} / 메모: {memo}")
        elif sentence:
            highlights.append(sentence)
    bookmarks = []
    for b in bookmark_rows:
        memo = (b.memo or '').strip()
        if memo:
            bookmarks.append(memo)

    stats['noteCount'] = len(notes)
    stats['noteCharacterCount'] = sum(len(note) for note in notes)
    stats['highlightCount'] = len(highlight_rows)
    stats['bookmarkCount'] = len(bookmark_rows)

    session_stats = db.query(
        func.coalesce(func.sum(ReadingSession.total_seconds), 0),
        func.min(ReadingSession.start_page),
        func.max(ReadingSession.end_page),
    ).filter(ReadingSession.user_id == user_id, ReadingSession.book_id == book_id).one()
    stats['totalReadingSeconds'] = int(session_stats[0] or 0)
    stats['startPage'] = int(session_stats[1]) if session_stats[1] is not None else None
    stats['endPage'] = int(session_stats[2]) if session_stats[2] is not None else None

    book = db.query(Book).filter(Book.id == book_id).first()
    author_rows = db.query(Author.name).join(BookAuthor, BookAuthor.author_id == Author.id).filter(BookAuthor.book_id == book_id).all()
    authors = [name for (name,) in author_rows]

    return ReadingSummaryPayload(
        summaryType=SUMMARY_TARGET_TYPE,
        bookId=book_id,
        trigger="auto",
        stats=stats,
        notes=notes,
        highlights=highlights,
        bookmarks=bookmarks,
        bookTitle=book.title if book else None,
        authors=authors,
    ).model_dump()


def is_auto_eligible(stats: dict[str, Any]) -> bool:
    return int(stats.get('noteCount') or 0) >= AUTO_MIN_NOTE_COUNT or int(stats.get('noteCharacterCount') or 0) >= AUTO_MIN_NOTE_CHARACTERS


def mark_summary_dirty(db: Session, user_id: int, book_id: int) -> BookReadingSummary:
    summary = get_or_create_summary(db, user_id, book_id)
    payload = collect_summary_inputs(db, user_id, book_id)
    summary.stats_json = payload['stats']
    summary.summary_dirty = True
    summary.last_source_updated_at = utcnow()
    if summary.status == ReadingSummaryStatus.READY:
        summary.status = ReadingSummaryStatus.READY
    elif is_auto_eligible(payload['stats']):
        summary.status = ReadingSummaryStatus.PENDING
    else:
        summary.status = ReadingSummaryStatus.NOT_READY
    db.commit()
    db.refresh(summary)
    return summary


def has_active_summary_job(db: Session, user_id: int, book_id: int) -> bool:
    return db.query(AIJob.id).filter(
        AIJob.user_id == user_id,
        AIJob.job_type == AIJobType.SUMMARY,
        AIJob.target_type == SUMMARY_TARGET_TYPE,
        AIJob.target_id == book_id,
        AIJob.status.in_([AIJobStatus.PENDING, AIJobStatus.RUNNING]),
    ).first() is not None


def enqueue_summary_job(db: Session, user_id: int, book_id: int, trigger: str) -> tuple[BookReadingSummary, bool, str | None]:
    summary = get_or_create_summary(db, user_id, book_id)
    payload = collect_summary_inputs(db, user_id, book_id)
    summary.stats_json = payload['stats']
    summary.last_source_updated_at = summary.last_source_updated_at or utcnow()
    auto_eligible = is_auto_eligible(payload['stats'])
    if trigger == 'auto' and not auto_eligible:
        summary.status = ReadingSummaryStatus.NOT_READY
        db.commit()
        return summary, False, 'AUTO_THRESHOLD_NOT_MET'
    if has_active_summary_job(db, user_id, book_id):
        summary.status = ReadingSummaryStatus.PROCESSING
        db.commit()
        return summary, False, 'ALREADY_QUEUED'

    payload['trigger'] = trigger
    job = AIJob(
        user_id=user_id,
        job_type=AIJobType.SUMMARY,
        status=AIJobStatus.PENDING,
        target_type=SUMMARY_TARGET_TYPE,
        target_id=book_id,
        payload=payload,
    )
    db.add(job)
    summary.summary_dirty = True
    summary.status = ReadingSummaryStatus.PENDING if trigger == 'auto' else ReadingSummaryStatus.PROCESSING
    db.commit()
    db.refresh(summary)
    return summary, True, None


def list_dirty_summaries_for_auto_queue(db: Session) -> list[BookReadingSummary]:
    cutoff = utcnow() - timedelta(minutes=AUTO_DEBOUNCE_MINUTES)
    candidates = db.query(BookReadingSummary).filter(
        BookReadingSummary.summary_dirty.is_(True),
        BookReadingSummary.last_source_updated_at.isnot(None),
        BookReadingSummary.last_source_updated_at <= cutoff,
    ).order_by(BookReadingSummary.last_source_updated_at.asc(), BookReadingSummary.id.asc()).limit(50).all()
    return candidates


def save_summary_result(db: Session, user_id: int, book_id: int, summary_content: dict[str, Any], stats: dict[str, Any]) -> BookReadingSummary:
    summary = get_or_create_summary(db, user_id, book_id)
    summary.summary_json = {
        'summary': summary_content.get('summary'),
        'keyPoints': summary_content.get('keyPoints') or [],
        'notesDigest': summary_content.get('notesDigest') or [],
    }
    summary.stats_json = stats
    summary.summary_dirty = False
    summary.status = ReadingSummaryStatus.READY
    summary.last_summarized_at = utcnow()
    summary.error_message = None
    db.commit()
    db.refresh(summary)
    create_notification(
        db,
        user_id,
        title='AI 독서 요약이 준비됐어요',
        body='남겨주신 메모를 바탕으로 책 요약을 정리했어요.',
        notification_type=NotificationType.AI_SUMMARY_READY,
        target_info={'bookId': book_id},
        data={'bookId': book_id},
        send_push=False,
    )
    return summary


def save_summary_failure(db: Session, user_id: int, book_id: int, error_message: str) -> BookReadingSummary:
    summary = get_or_create_summary(db, user_id, book_id)
    summary.status = ReadingSummaryStatus.FAILED
    summary.error_message = error_message
    db.commit()
    db.refresh(summary)
    return summary


def delete_summary_data(db: Session, user_id: int, book_id: int) -> tuple[bool, int, int]:
    summary = db.query(BookReadingSummary).filter(
        BookReadingSummary.user_id == user_id,
        BookReadingSummary.book_id == book_id,
    ).first()

    deleted_jobs = (
        db.query(AIJob)
        .filter(
            AIJob.user_id == user_id,
            AIJob.job_type == AIJobType.SUMMARY,
            AIJob.target_type == SUMMARY_TARGET_TYPE,
            AIJob.target_id == book_id,
        )
        .delete(synchronize_session=False)
    )

    from app.models import Notification

    deleted_notifications = 0
    notifications = db.query(Notification).filter(
        Notification.user_id == user_id,
        Notification.type == NotificationType.AI_SUMMARY_READY,
    ).all()
    for notification in notifications:
        target = notification.target_info or {}
        data = notification.data or {}
        target_book_id = target.get('bookId') or data.get('bookId')
        if str(target_book_id) == str(book_id):
            db.delete(notification)
            deleted_notifications += 1

    deleted = False
    if summary:
        db.delete(summary)
        deleted = True

    db.commit()
    return deleted, int(deleted_jobs or 0), deleted_notifications
