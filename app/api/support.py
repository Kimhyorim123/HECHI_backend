from datetime import datetime

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.core.auth import get_current_user, get_admin_user
from app.database import get_db
from app.models import User, FAQ, SupportTicket, SupportTicketStatus
from pydantic import BaseModel, Field, ConfigDict

router = APIRouter(prefix="/support", tags=["support"])


class FAQCreate(BaseModel):
    question: str = Field(..., min_length=1)
    answer: str = Field(..., min_length=1)
    is_pinned: bool = True


class FAQResponse(BaseModel):
    id: int
    question: str
    answer: str
    is_pinned: bool
    model_config = ConfigDict(from_attributes=True)


class TicketCreate(BaseModel):
    title: str = Field(..., min_length=1)
    description: str = Field(..., min_length=1)


class TicketResponse(BaseModel):
    id: int
    user_id: int
    title: str
    description: str
    reply: str | None = None
    status: str
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)


class TicketAnswer(BaseModel):
    reply: str = Field(..., min_length=1)
    close: bool = Field(False, description="답변 후 즉시 종료 처리 여부")


@router.get("/faqs", response_model=list[FAQResponse])
def list_faqs(db: Session = Depends(get_db)):
    rows = (
        db.query(FAQ)
        .filter(FAQ.is_pinned == True)  # noqa: E712
        .order_by(FAQ.id.asc())
        .limit(7)
        .all()
    )
    return rows


@router.post("/faqs", response_model=FAQResponse)
def create_faq(
    payload: FAQCreate,
    db: Session = Depends(get_db),
    admin: User = Depends(get_admin_user),
):
    # 운영용: 인증된 사용자만 등록 (권한 체크는 추후 추가)
    faq = FAQ(question=payload.question, answer=payload.answer, is_pinned=payload.is_pinned)
    db.add(faq)
    db.commit()
    db.refresh(faq)
    return faq


@router.post("/tickets", response_model=TicketResponse, status_code=status.HTTP_201_CREATED)
def create_ticket(
    payload: TicketCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    ticket = SupportTicket(
        user_id=current_user.id,
        title=payload.title,
        description=payload.description,
        status=SupportTicketStatus.OPEN,
    )
    db.add(ticket)
    db.commit()
    db.refresh(ticket)
    return ticket


@router.get("/tickets/me", response_model=list[TicketResponse])
def my_tickets(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    rows = (
        db.query(SupportTicket)
        .filter(SupportTicket.user_id == current_user.id)
        .order_by(SupportTicket.id.desc())
        .all()
    )
    return rows


@router.get("/tickets", response_model=list[TicketResponse], summary="전체 문의 목록(관리자)")
def list_all_tickets(
    status_filter: str | None = None,
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
    return q.order_by(SupportTicket.id.desc()).all()


@router.patch("/tickets/{ticket_id}/answer", response_model=TicketResponse, summary="문의 답변 등록/종료(관리자)")
def answer_ticket(
    ticket_id: int,
    payload: TicketAnswer,
    db: Session = Depends(get_db),
    admin: User = Depends(get_admin_user),
):
    t = db.query(SupportTicket).filter(SupportTicket.id == ticket_id).first()
    if not t:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Ticket not found")
    t.reply = payload.reply
    t.status = SupportTicketStatus.CLOSED if payload.close else SupportTicketStatus.ANSWERED
    db.commit()
    db.refresh(t)
    return t
