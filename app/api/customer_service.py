from fastapi import APIRouter, Depends, UploadFile, File, Form, HTTPException, status
from sqlalchemy.orm import Session
from typing import Optional, Literal
from datetime import datetime
import csv
from io import StringIO
from fastapi.responses import StreamingResponse
import os

from app.core.auth import get_current_user, get_admin_user
from app.database import get_db
from app.models import (
    FAQ,
    SupportTicket,
    SupportTicketStatus,
    User,
    SupportTicketLog,
    SupportTicketAction,
    SupportTicketAnswerHistory,
)
from app.services.notify import create_notification

router = APIRouter(prefix="/customer-service", tags=["customer-service"]) 

# ---- Helpers ----
ALLOWED_EXTS = {".jpg", ".jpeg", ".png", ".pdf"}
MAX_SIZE_MB = 5
UPLOAD_DIR = os.environ.get("UPLOAD_DIR", os.path.abspath(os.path.join(os.getcwd(), "uploads")))
STATIC_BASE_URL = os.environ.get("STATIC_BASE_URL", "/static/uploads/")

os.makedirs(UPLOAD_DIR, exist_ok=True)

def _ext_ok(filename: str) -> bool:
    _, ext = os.path.splitext(filename.lower())
    return ext in ALLOWED_EXTS

async def _save_upload(file: UploadFile) -> str:
    # size check: read into chunks to avoid memory spike
    size = 0
    fn = file.filename or "upload"
    if not _ext_ok(fn):
        raise HTTPException(status_code=400, detail="Only jpg/png/pdf allowed")
    # store with deterministic safe name
    import uuid
    key = f"{uuid.uuid4().hex}{os.path.splitext(fn)[1].lower()}"
    dest_path = os.path.join(UPLOAD_DIR, key)
    with open(dest_path, "wb") as out:
        while True:
            chunk = await file.read(1024 * 1024)
            if not chunk:
                break
            size += len(chunk)
            if size > MAX_SIZE_MB * 1024 * 1024:
                try:
                    os.remove(dest_path)
                except Exception:
                    pass
                raise HTTPException(status_code=413, detail="File too large")
            out.write(chunk)
    # Return URL (in production map to CDN/S3)
    return f"{STATIC_BASE_URL}{key}"

# ---- DTO mappers (domain-based keys) ----

def _faq_to_domain(f: FAQ) -> dict:
    return {
        "faqId": f.id,
        "question": f.question,
        "answer": f.answer,
    }

def _status_to_domain(s: SupportTicketStatus) -> Literal["waiting","answered"] | str:
    if s == SupportTicketStatus.OPEN:
        return "waiting"
    if s == SupportTicketStatus.ANSWERED:
        return "answered"
    # CLOSED는 운영용: answered로 간주
    return "answered" if s == SupportTicketStatus.CLOSED else str(s)


def _ticket_to_domain(t: SupportTicket, db: Optional[Session] = None) -> dict:
    responder_name: Optional[str] = None
    if t.responded_by and db is not None:
        u = db.query(User).filter(User.id == t.responded_by).first()
        responder_name = u.name if u else None
    return {
        "inquiryId": t.id,
        "userId": t.user_id,
        "inquiryTitle": t.title,
        "inquiryDescription": t.description,
        "inquiryFileUrl": t.attachment_url,
        "status": _status_to_domain(t.status),
        "inquiryAnswer": t.reply,
        "inquiryCreatedAt": t.created_at.isoformat() if t.created_at else None,
        "inquiryAnsweredAt": t.responded_at.isoformat() if t.responded_at else None,
        "responderUserId": t.responded_by,
        "responderName": responder_name,
    }

# ---- Endpoints ----

@router.get("/faqs", summary="자주 묻는 질문 조회")
def get_faqs(db: Session = Depends(get_db)):
    rows = (
        db.query(FAQ)
        .filter(FAQ.is_pinned == True)  # noqa: E712
        .order_by(FAQ.id.asc())
        .limit(7)
        .all()
    )
    return {"faqs": [_faq_to_domain(f) for f in rows]}


@router.get("/my", summary="현재 사용자 문의 내역 조회")
def list_my(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    rows = (
        db.query(SupportTicket)
        .filter(SupportTicket.user_id == current_user.id)
        .order_by(SupportTicket.id.desc())
        .all()
    )
    return {"inquiries": [_ticket_to_domain(t) for t in rows]}


@router.post("/my", status_code=status.HTTP_201_CREATED, summary="사용자 문의 등록")
async def create_my(
    inquiryTitle: str = Form(...),
    inquiryDescription: str = Form(...),
    inquiryFile: Optional[UploadFile] = File(None),
    inquiryFileUrl: Optional[str] = Form(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    file_url: Optional[str] = None
    # If presigned upload is used, take URL directly; else accept direct file upload.
    if inquiryFileUrl:
        file_url = inquiryFileUrl
    elif inquiryFile is not None:
        file_url = await _save_upload(inquiryFile)
    t = SupportTicket(
        user_id=current_user.id,
        title=inquiryTitle,
        description=inquiryDescription,
        attachment_url=file_url,
        status=SupportTicketStatus.OPEN,
    )
    db.add(t)
    db.commit()
    db.refresh(t)
    # activity log
    db.add(SupportTicketLog(ticket_id=t.id, actor_user_id=current_user.id, action=SupportTicketAction.CREATE, message="ticket created"))
    db.commit()
    return _ticket_to_domain(t)


@router.get("/admin", summary="관리자 문의 리스트 조회")
def admin_list(
    status_filter: Optional[str] = None,
    page: int = 1,
    size: int = 20,
    db: Session = Depends(get_db),
    admin: User = Depends(get_admin_user),
):
    q = db.query(SupportTicket)
    if status_filter:
        try:
            st = SupportTicketStatus(status_filter)
            q = q.filter(SupportTicket.status == st)
        except Exception:
            pass
    page = max(1, page)
    size = max(1, min(100, size))
    rows = q.order_by(SupportTicket.id.desc()).offset((page - 1) * size).limit(size).all()
    return {"inquiries": [_ticket_to_domain(t, db) for t in rows]}


@router.get("/admin/summary", summary="문의 상태별 카운트 요약")
def admin_summary(
    db: Session = Depends(get_db),
    admin: User = Depends(get_admin_user),
):
    from sqlalchemy import func
    rows = (
        db.query(SupportTicket.status, func.count(SupportTicket.id))
        .group_by(SupportTicket.status)
        .all()
    )
    waiting = 0
    answered = 0
    for st, cnt in rows:
        if st == SupportTicketStatus.OPEN:
            waiting += cnt
        elif st in (SupportTicketStatus.ANSWERED, SupportTicketStatus.CLOSED):
            answered += cnt
    return {"waiting": waiting, "answered": answered, "total": waiting + answered}


@router.post("/admin", summary="관리자 답변 등록")
def admin_answer(
    body: dict,
    db: Session = Depends(get_db),
    admin: User = Depends(get_admin_user),
):
    inquiry_id = body.get("inquiryId")
    inquiry_answer = body.get("inquiryAnswer")
    if not inquiry_id or not inquiry_answer:
        raise HTTPException(status_code=400, detail="inquiryId and inquiryAnswer are required")
    t = db.query(SupportTicket).filter(SupportTicket.id == inquiry_id).first()
    if not t:
        raise HTTPException(status_code=404, detail="Inquiry not found")
    prev = t.reply
    t.reply = inquiry_answer
    t.status = SupportTicketStatus.ANSWERED
    t.responded_by = admin.id if hasattr(admin, "id") else None
    t.responded_at = datetime.utcnow()
    db.commit()
    db.refresh(t)
    # log add/update depending on prev
    action = SupportTicketAction.ANSWER_UPDATE if prev else SupportTicketAction.ANSWER_ADD
    db.add(SupportTicketLog(ticket_id=t.id, actor_user_id=(admin.id if hasattr(admin, "id") else None), action=action, message="answer saved"))
    # history record
    db.add(SupportTicketAnswerHistory(ticket_id=t.id, responder_user_id=(admin.id if hasattr(admin, "id") else None), answer_text=inquiry_answer))
    # notify user
    try:
        create_notification(db, t.user_id, title="문의 답변이 도착했어요", body=t.title, data={"inquiryId": t.id})
    except Exception:
        pass
    db.commit()
    return _ticket_to_domain(t, db)

@router.delete("/admin", summary="관리자 답변 삭제")
def admin_delete_answer(
    body: dict,
    db: Session = Depends(get_db),
    admin: User = Depends(get_admin_user),
):
    inquiry_id = body.get("inquiryId")
    if not inquiry_id:
        raise HTTPException(status_code=400, detail="inquiryId is required")
    t = db.query(SupportTicket).filter(SupportTicket.id == inquiry_id).first()
    if not t:
        raise HTTPException(status_code=404, detail="Inquiry not found")
    t.reply = None
    t.status = SupportTicketStatus.OPEN
    t.responded_by = None
    t.responded_at = None
    db.commit()
    db.add(SupportTicketLog(ticket_id=t.id, actor_user_id=(admin.id if hasattr(admin, "id") else None), action=SupportTicketAction.ANSWER_DELETE, message="answer deleted"))
    db.commit()
    return {"ok": True}


@router.get("/admin/logs", summary="활동 로그 조회")
def admin_logs(
    ticket_id: Optional[int] = None,
    action: Optional[str] = None,
    page: int = 1,
    size: int = 20,
    db: Session = Depends(get_db),
    admin: User = Depends(get_admin_user),
):
    q = db.query(SupportTicketLog)
    if ticket_id:
        q = q.filter(SupportTicketLog.ticket_id == ticket_id)
    if action:
        try:
            act = SupportTicketAction(action)
            q = q.filter(SupportTicketLog.action == act)
        except Exception:
            pass
    page = max(1, page)
    size = max(1, min(100, size))
    rows = q.order_by(SupportTicketLog.id.desc()).offset((page - 1) * size).limit(size).all()
    def to_dict(r: SupportTicketLog):
        return {
            "ticketId": r.ticket_id,
            "actorUserId": r.actor_user_id,
            "action": r.action.value if hasattr(r.action, "value") else str(r.action),
            "message": r.message,
            "createdAt": r.created_at.isoformat() if r.created_at else None,
        }
    return {"logs": [to_dict(r) for r in rows]}


@router.get("/admin/answers/{ticket_id}", summary="답변 이력 조회")
def admin_answer_history(
    ticket_id: int,
    page: int = 1,
    size: int = 20,
    db: Session = Depends(get_db),
    admin: User = Depends(get_admin_user),
):
    q = db.query(SupportTicketAnswerHistory).filter(SupportTicketAnswerHistory.ticket_id == ticket_id)
    page = max(1, page)
    size = max(1, min(100, size))
    rows = q.order_by(SupportTicketAnswerHistory.id.desc()).offset((page - 1) * size).limit(size).all()
    def to_dict(h: SupportTicketAnswerHistory):
        return {
            "ticketId": h.ticket_id,
            "responderUserId": h.responder_user_id,
            "answer": h.answer_text,
            "answeredAt": h.answered_at.isoformat() if h.answered_at else None,
        }
    return {"answers": [to_dict(h) for h in rows]}

@router.get("/admin/search", summary="관리자 문의 검색/기간 필터")
def admin_search(
    q: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    page: int = 1,
    size: int = 20,
    db: Session = Depends(get_db),
    admin: User = Depends(get_admin_user),
):
    query = db.query(SupportTicket)
    if q:
        like = f"%{q}%"
        from sqlalchemy import or_
        query = query.filter(or_(SupportTicket.title.like(like), SupportTicket.description.like(like)))
    if date_from:
        try:
            dt_from = datetime.fromisoformat(date_from)
            query = query.filter(SupportTicket.created_at >= dt_from)
        except Exception:
            pass
    if date_to:
        try:
            dt_to = datetime.fromisoformat(date_to)
            query = query.filter(SupportTicket.created_at <= dt_to)
        except Exception:
            pass
    page = max(1, page)
    size = max(1, min(100, size))
    rows = query.order_by(SupportTicket.id.desc()).offset((page - 1) * size).limit(size).all()
    return {"inquiries": [_ticket_to_domain(t, db) for t in rows]}


@router.get("/admin/export.csv", summary="관리자 CSV 내보내기")
def admin_export_csv(
    q: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    status_filter: Optional[str] = None,
    db: Session = Depends(get_db),
    admin: User = Depends(get_admin_user),
):
    query = db.query(SupportTicket)
    if q:
        like = f"%{q}%"
        from sqlalchemy import or_
        query = query.filter(or_(SupportTicket.title.like(like), SupportTicket.description.like(like)))
    if date_from:
        try:
            dt_from = datetime.fromisoformat(date_from)
            query = query.filter(SupportTicket.created_at >= dt_from)
        except Exception:
            pass
    if date_to:
        try:
            dt_to = datetime.fromisoformat(date_to)
            query = query.filter(SupportTicket.created_at <= dt_to)
        except Exception:
            pass
    if status_filter:
        try:
            st = SupportTicketStatus(status_filter)
            query = query.filter(SupportTicket.status == st)
        except Exception:
            pass

    rows = query.order_by(SupportTicket.id.desc()).all()
    # build CSV
    buf = StringIO()
    writer = csv.writer(buf)
    writer.writerow([
        "inquiryId","userId","title","description","status","answer","createdAt","answeredAt","responderUserId"
    ])
    for t in rows:
        writer.writerow([
            t.id, t.user_id, t.title, t.description, t.status.value if hasattr(t.status, 'value') else str(t.status),
            t.reply or "", t.created_at.isoformat() if t.created_at else "", t.responded_at.isoformat() if t.responded_at else "",
            t.responded_by or ""
        ])
    buf.seek(0)
    headers = {"Content-Disposition": "attachment; filename=customer-service-export.csv"}
    return StreamingResponse(iter([buf.getvalue()]), media_type="text/csv", headers=headers)
