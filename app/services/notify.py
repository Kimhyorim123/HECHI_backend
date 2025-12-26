from sqlalchemy.orm import Session
from typing import Optional, Dict, Any

from app.models import Notification, NotificationType


def create_notification(db: Session, user_id: int, title: Optional[str], body: str, data: Optional[Dict[str, Any]] = None):
    n = Notification(user_id=user_id, type=NotificationType.GENERAL, title=title, body=body, data=data or {})
    db.add(n)
    db.commit()
    return n
