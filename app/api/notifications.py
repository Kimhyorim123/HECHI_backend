from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.core.auth import get_current_user
from app.models import User
from app.services.notifications import send_to_token

router = APIRouter(prefix="/notifications", tags=["notifications"])


class TokenUpdateRequest(BaseModel):
    fcm_token: str


class SendTestRequest(BaseModel):
    title: str
    body: str
    data: dict | None = None


@router.post("/register-token")
def register_token(payload: TokenUpdateRequest, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    current_user.fcm_token = payload.fcm_token
    db.add(current_user)
    db.commit()
    return {"ok": True}


@router.post("/send-test")
def send_test(payload: SendTestRequest, current_user: User = Depends(get_current_user)):
    if not current_user.fcm_token:
        raise HTTPException(status_code=400, detail="No FCM token registered for user")
    mid = send_to_token(current_user.fcm_token, payload.title, payload.body, payload.data or None)
    return {"message_id": mid}
