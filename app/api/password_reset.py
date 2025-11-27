from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from pydantic import BaseModel, EmailStr

from app.database import get_db
from app.models import User
from app.core.security import hash_password

router = APIRouter(prefix="/auth/password-reset", tags=["auth"])


class ResetRequest(BaseModel):
    email: EmailStr


class ResetConfirm(BaseModel):
    email: EmailStr
    new_password: str


@router.post("/request")
def request_reset(data: ResetRequest, db: Session = Depends(get_db)):
    exists = db.query(User).filter(User.email == data.email).first()
    return {"exists": bool(exists)}


@router.post("/confirm")
def confirm_reset(data: ResetConfirm, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == data.email).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Email not found")
    user.password_hash = hash_password(data.new_password)
    db.commit()
    return {"ok": True}
