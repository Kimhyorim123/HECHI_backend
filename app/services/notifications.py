from __future__ import annotations

from typing import Optional

import firebase_admin
from firebase_admin import credentials, messaging

from app.core.config import get_settings

_initialized = False


def _ensure_initialized() -> None:
    global _initialized
    if _initialized:
        return
    settings = get_settings()
    sa_path: Optional[str] = settings.fcm_service_account_json_path
    if not sa_path:
        # Allow running without FCM configured
        return
    if not firebase_admin._apps:  # type: ignore[attr-defined]
        cred = credentials.Certificate(sa_path)
        firebase_admin.initialize_app(cred)
    _initialized = True


def send_to_token(token: str, title: str, body: str, data: Optional[dict] = None) -> Optional[str]:
    """Send a notification to a single FCM token. Returns message ID or None if FCM not configured."""
    _ensure_initialized()
    if not firebase_admin._apps:  # type: ignore[attr-defined]
        return None
    message = messaging.Message(
        token=token,
        notification=messaging.Notification(title=title, body=body),
        data={k: str(v) for k, v in (data or {}).items()},
    )
    return messaging.send(message)


def send_to_topic(topic: str, title: str, body: str, data: Optional[dict] = None) -> Optional[str]:
    _ensure_initialized()
    if not firebase_admin._apps:  # type: ignore[attr-defined]
        return None
    message = messaging.Message(
        topic=topic,
        notification=messaging.Notification(title=title, body=body),
        data={k: str(v) for k, v in (data or {}).items()},
    )
    return messaging.send(message)
