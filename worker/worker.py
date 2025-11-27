"""간단한 Worker 스켈레톤.
실행: python -m worker.worker
TODO:
- OpenAI 요약/추천 Job 처리
- FCM 알림 발송 처리
- 재시도/백오프 전략
"""
from time import sleep
from datetime import datetime
from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.models import AIJob, AIJobStatus, Notification

POLL_INTERVAL_SECONDS = 5


def process_ai_jobs(db: Session):
    pending_jobs = (
        db.query(AIJob)
        .filter(AIJob.status == AIJobStatus.PENDING)
        .order_by(AIJob.created_at.asc())
        .limit(10)
        .all()
    )
    for job in pending_jobs:
        # 실제 OpenAI 호출은 추후 구현
        job.status = AIJobStatus.RUNNING
        db.commit()
        try:
            # PLACEHOLDER 처리 로직
            job.result = {"message": "stub result", "processed_at": datetime.utcnow().isoformat()}
            job.status = AIJobStatus.SUCCESS
        except Exception as e:  # noqa: BLE001
            job.status = AIJobStatus.FAILED
            job.error_message = str(e)
        finally:
            db.commit()


def process_notifications(db: Session):
    # 알림 전송 로직 추후: FCM HTTP v1 API
    pending_notis = db.query(Notification).filter(Notification.is_read == False).limit(10).all()  # noqa: E712
    # 여기서는 단순히 로그 출력 정도만
    for n in pending_notis:
        # TODO: 실제 FCM 토큰 조회 후 발송
        print(f"[NOTIFICATION STUB] Would send: {n.title or n.type} to user {n.user_id}")
        n.is_read = True  # 임시로 읽음 처리
    db.commit()


def main_loop():
    while True:
        db = SessionLocal()
        try:
            process_ai_jobs(db)
            process_notifications(db)
        finally:
            db.close()
        sleep(POLL_INTERVAL_SECONDS)


if __name__ == "__main__":
    print("Worker started...")
    main_loop()
