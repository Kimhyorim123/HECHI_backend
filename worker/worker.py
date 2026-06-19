"""간단한 Worker 스켈레톤.
실행: python -m worker.worker
"""
from time import sleep
from datetime import datetime, timedelta, timezone
from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.models import AIJob, AIJobStatus, AIJobType, Book, FCMToken, Group, GroupMember, GroupPost, NotificationType, ReadingSession, ReadingStatus, ReadingSummaryStatus, User, UserBook
from app.services.notify import create_notification
from app.services.aladin_recommend_sync import sync_aladin_recommendation_lists
from app.services.openai_summary import generate_reading_summary
from app.services.reading_summary import (
    SUMMARY_TARGET_TYPE,
    collect_summary_inputs,
    enqueue_summary_job,
    list_dirty_summaries_for_auto_queue,
    save_summary_failure,
    save_summary_result,
)

POLL_INTERVAL_SECONDS = 300
READING_REMINDER_DAYS = 3
READING_SLUMP_DAYS = 7
READING_SLUMP_MIN_OPEN_BOOKS = 3
GROUP_DISCUSSION_DEADLINE_HOURS = 24
KST = timezone(timedelta(hours=9))


def process_summary_auto_queue(db: Session):
    candidates = list_dirty_summaries_for_auto_queue(db)
    for summary in candidates:
        enqueue_summary_job(db, summary.user_id, summary.book_id, trigger='auto')


def process_ai_jobs(db: Session):
    pending_jobs = (
        db.query(AIJob)
        .filter(AIJob.status == AIJobStatus.PENDING)
        .order_by(AIJob.created_at.asc())
        .limit(10)
        .all()
    )
    for job in pending_jobs:
        job.status = AIJobStatus.RUNNING
        job.attempt = int(job.attempt or 0) + 1
        db.commit()
        try:
            if job.job_type == AIJobType.SUMMARY and job.target_type == SUMMARY_TARGET_TYPE:
                from app.services.reading_summary import get_or_create_summary
                summary = get_or_create_summary(db, job.user_id, int(job.target_id))
                summary.status = ReadingSummaryStatus.PROCESSING
                db.commit()
                payload = job.payload or collect_summary_inputs(db, job.user_id, int(job.target_id))
                summary_content = generate_reading_summary(payload)
                save_summary_result(db, job.user_id, int(job.target_id), summary_content, payload.get('stats') or {})
                job.result = summary_content
            else:
                job.result = {"message": "stub result", "processed_at": datetime.utcnow().isoformat()}
            job.status = AIJobStatus.SUCCESS
            job.error_message = None
        except Exception as e:  # noqa: BLE001
            job.status = AIJobStatus.FAILED
            job.error_message = str(e)
            if job.job_type == AIJobType.SUMMARY and job.target_type == SUMMARY_TARGET_TYPE and job.target_id is not None:
                save_summary_failure(db, job.user_id, int(job.target_id), str(e))
        finally:
            db.commit()


def _utcnow() -> datetime:
    return datetime.utcnow()


def _kst_now() -> datetime:
    return datetime.now(KST)


def _reading_reminder_title(book_title: str | None) -> str:
    clean_title = (book_title or "").strip()
    if not clean_title:
        return "오늘은 어떤 책을 펼쳐볼까요?"
    return f'"{clean_title}" 잊으신 건 아니죠? 👀'


def _parse_discussion_ends_at(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def process_group_discussion_deadlines(db: Session):
    now = _utcnow().replace(tzinfo=timezone.utc)
    deadline_cutoff = now + timedelta(hours=GROUP_DISCUSSION_DEADLINE_HOURS)
    posts = db.query(GroupPost).filter(GroupPost.discussion.isnot(None)).all()
    for post in posts:
        discussion = post.discussion or {}
        ends_at = _parse_discussion_ends_at(discussion.get('endsAt'))
        if not ends_at:
            continue
        if ends_at <= now or ends_at > deadline_cutoff:
            continue
        group = db.query(Group).filter(Group.id == post.group_id).first()
        if not group:
            continue
        recipient_user_ids = [row[0] for row in db.query(GroupMember.user_id).filter(GroupMember.group_id == group.id).all()]
        book = db.query(Book).filter(Book.id == post.book_id).first() if post.book_id else None
        payload = {
            'groupId': group.group_id,
            'postId': post.id,
            'eventKind': 'GROUP_DISCUSSION_DEADLINE',
            'discussionEndsAt': ends_at.isoformat(),
        }
        for user_id in recipient_user_ids:
            create_notification(
                db,
                user_id,
                title=f'{group.name} 토론',
                body='토론 마감이 얼마 남지 않았어요.',
                notification_type=NotificationType.GROUP_DISCUSSION,
                target_info=payload,
                data=payload,
                thumbnail_url=(book.thumbnail or book.small_thumbnail) if book else None,
                send_push=True,
            )


def process_reading_reports(db: Session):
    now_kst = _kst_now()
    if now_kst.day != 1:
        return

    prev_month_last_day = now_kst.replace(day=1) - timedelta(days=1)
    prev_month_start = prev_month_last_day.replace(day=1).date()
    prev_month_end = prev_month_last_day.date()
    prev_year = now_kst.year - 1
    prev_year_start = datetime(prev_year, 1, 1, tzinfo=KST).date()
    prev_year_end = datetime(prev_year, 12, 31, tzinfo=KST).date()

    user_ids = [row[0] for row in db.query(User.id).all()]
    for user_id in user_ids:
        monthly_count = (
            db.query(ReadingSession.id)
            .filter(
                ReadingSession.user_id == user_id,
                ReadingSession.end_time.isnot(None),
                ReadingSession.end_time >= prev_month_start,
                ReadingSession.end_time <= prev_month_end,
            )
            .count()
        )
        if monthly_count > 0:
            payload = {
                'eventKind': 'READING_REPORT_MONTHLY',
                'reportKind': 'MONTHLY',
                'reportYear': prev_month_last_day.year,
                'reportMonth': prev_month_last_day.month,
            }
            create_notification(
                db,
                user_id,
                title='지난달 독서 결산이 도착했어요',
                body='지난달의 독서 기록을 한 번에 확인해보세요.',
                notification_type=NotificationType.READING_REPORT,
                target_info=payload,
                data=payload,
                send_push=True,
            )

        if now_kst.month == 1:
            yearly_count = (
                db.query(ReadingSession.id)
                .filter(
                    ReadingSession.user_id == user_id,
                    ReadingSession.end_time.isnot(None),
                    ReadingSession.end_time >= prev_year_start,
                    ReadingSession.end_time <= prev_year_end,
                )
                .count()
            )
            if yearly_count > 0:
                payload = {
                    'eventKind': 'READING_REPORT_YEARLY',
                    'reportKind': 'YEARLY',
                    'reportYear': prev_year,
                }
                create_notification(
                    db,
                    user_id,
                    title='지난해 독서 결산이 도착했어요',
                    body='지난해의 독서 기록을 한 번에 확인해보세요.',
                    notification_type=NotificationType.READING_REPORT,
                    target_info=payload,
                    data=payload,
                    send_push=True,
                )


def process_reading_slumps(db: Session) -> set[int]:
    cutoff = datetime.utcnow() - timedelta(days=READING_SLUMP_DAYS)
    users = (
        db.query(User)
        .join(FCMToken, FCMToken.user_id == User.id)
        .filter(FCMToken.is_active.is_(True))
        .distinct()
        .all()
    )
    today = datetime.utcnow().date().isoformat()
    notified_user_ids: set[int] = set()
    open_statuses = [ReadingStatus.PENDING, ReadingStatus.READING, ReadingStatus.PAUSED]

    for user in users:
        last_session = (
            db.query(ReadingSession)
            .filter(ReadingSession.user_id == user.id)
            .order_by(ReadingSession.end_time.desc(), ReadingSession.id.desc())
            .first()
        )
        if last_session and last_session.end_time and last_session.end_time >= cutoff:
            continue

        open_books = (
            db.query(UserBook)
            .filter(UserBook.user_id == user.id, UserBook.status.in_(open_statuses))
            .order_by(UserBook.updated_at.desc(), UserBook.id.desc())
            .all()
        )
        if len(open_books) < READING_SLUMP_MIN_OPEN_BOOKS:
            continue

        candidate = next((item for item in open_books if item.status in {ReadingStatus.READING, ReadingStatus.PAUSED}), open_books[0])
        payload = {
            "reminderType": "READING_SLUMP",
            "reminderDate": today,
            "openBookCount": len(open_books),
        }
        thumbnail = None
        if candidate.book_id is not None:
            book = db.query(Book).filter(Book.id == candidate.book_id).first()
            payload["bookId"] = candidate.book_id
            if book:
                payload["bookTitle"] = book.title
                thumbnail = book.thumbnail or book.small_thumbnail
                if thumbnail:
                    payload["thumbnailUrl"] = thumbnail

        create_notification(
            db,
            user.id,
            title="너무 많은 책에 치여 잠시 쉬고 계신가요?",
            body="보관함에서 한 권만 꼭 집어 다시 시작해 봐요! 🙌",
            notification_type=NotificationType.READING_SLUMP,
            target_info=payload,
            data=payload,
            thumbnail_url=thumbnail,
            send_push=True,
        )
        notified_user_ids.add(user.id)

    return notified_user_ids


def process_reading_reminders(db: Session, skip_user_ids: set[int] | None = None):
    cutoff = datetime.utcnow() - timedelta(days=READING_REMINDER_DAYS)
    users = (
        db.query(User)
        .join(FCMToken, FCMToken.user_id == User.id)
        .filter(FCMToken.is_active.is_(True))
        .distinct()
        .all()
    )
    today = datetime.utcnow().date().isoformat()
    skip_user_ids = skip_user_ids or set()
    for user in users:
        if user.id in skip_user_ids:
            continue
        has_books = db.query(UserBook.id).filter(UserBook.user_id == user.id).first() is not None
        if not has_books:
            continue
        last_session = (
            db.query(ReadingSession)
            .filter(ReadingSession.user_id == user.id)
            .order_by(ReadingSession.end_time.desc(), ReadingSession.id.desc())
            .first()
        )
        if last_session and last_session.end_time and last_session.end_time >= cutoff:
            continue

        reminder_payload = {
            "reminderType": "READING_REMINDER",
            "reminderDate": today,
        }
        reminder_thumbnail = None
        reminder_title = "오늘은 어떤 책을 펼쳐볼까요?"

        reading_books = (
            db.query(UserBook, Book)
            .join(Book, Book.id == UserBook.book_id)
            .filter(UserBook.user_id == user.id, UserBook.status == ReadingStatus.READING)
            .order_by(UserBook.updated_at.desc(), UserBook.id.desc())
            .limit(5)
            .all()
        )
        book_covers = []
        seen_covers = set()
        for _, reading_book in reading_books:
            cover = reading_book.thumbnail or reading_book.small_thumbnail
            if cover and cover not in seen_covers:
                seen_covers.add(cover)
                book_covers.append(cover)
            if len(book_covers) >= 3:
                break
        reminder_payload["bookCovers"] = book_covers

        if last_session and last_session.book_id is not None:
            book = db.query(Book).filter(Book.id == last_session.book_id).first()
            reminder_payload["bookId"] = last_session.book_id
            if book:
                reminder_payload["bookTitle"] = book.title
                reminder_title = _reading_reminder_title(book.title)
                reminder_thumbnail = book.thumbnail or book.small_thumbnail
                if reminder_thumbnail:
                    reminder_payload["thumbnailUrl"] = reminder_thumbnail

        create_notification(
            db,
            user.id,
            title=reminder_title,
            body="읽던 책의 다음 페이지가 기다리고 있어요.",
            notification_type=NotificationType.GENERAL,
            target_info=reminder_payload,
            data=reminder_payload,
            thumbnail_url=reminder_thumbnail,
            send_push=True,
        )


def process_aladin_recommendation_lists(db: Session):
    result = sync_aladin_recommendation_lists(db)
    if result:
        print(f"[worker] synced Aladin recommendation lists: {result}")


def main_loop():
    while True:
        db = SessionLocal()
        try:
            process_aladin_recommendation_lists(db)
            process_summary_auto_queue(db)
            process_ai_jobs(db)
            process_group_discussion_deadlines(db)
            process_reading_reports(db)
            slump_notified_users = process_reading_slumps(db)
            process_reading_reminders(db, skip_user_ids=slump_notified_users)
        finally:
            db.close()
        sleep(POLL_INTERVAL_SECONDS)


if __name__ == "__main__":
    print("Worker started...")
    main_loop()
