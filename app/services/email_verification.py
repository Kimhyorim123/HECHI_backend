from __future__ import annotations

from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
import hashlib
import hmac
import secrets
import smtplib

from ..core.config import get_settings


def smtp_enabled() -> bool:
    settings = get_settings()
    return bool(
        settings.smtp_host
        and settings.smtp_port
        and settings.smtp_username
        and settings.smtp_password
        and settings.smtp_from_email
    )


def generate_verification_code() -> str:
    return f"{secrets.randbelow(1_000_000):06d}"


def hash_verification_code(code: str) -> str:
    settings = get_settings()
    digest = hashlib.sha256(f"{settings.secret_key}:{code}".encode("utf-8")).hexdigest()
    return digest


def verify_verification_code(code: str, expected_hash: str | None) -> bool:
    if not expected_hash:
        return False
    actual_hash = hash_verification_code(code)
    return hmac.compare_digest(actual_hash, expected_hash)


def verification_expiry() -> datetime:
    settings = get_settings()
    return datetime.now(timezone.utc) + timedelta(minutes=settings.email_verification_exp_minutes)


def can_resend(sent_at: datetime | None) -> bool:
    if sent_at is None:
        return True
    settings = get_settings()
    now = datetime.now(timezone.utc)
    if sent_at.tzinfo is None:
        sent_at = sent_at.replace(tzinfo=timezone.utc)
    return (now - sent_at).total_seconds() >= settings.email_verification_resend_seconds


def send_verification_email(recipient_email: str, code: str) -> None:
    settings = get_settings()
    if not smtp_enabled():
        raise RuntimeError("SMTP is not configured")

    msg = EmailMessage()
    msg["Subject"] = "[BookStopper] 이메일 인증 코드"
    msg["From"] = settings.smtp_from_email
    msg["To"] = recipient_email
    msg.set_content(
        (
            "BookStopper 이메일 인증 코드입니다.\n\n"
            f"인증 코드: {code}\n"
            f"{settings.email_verification_exp_minutes}분 안에 입력해주세요.\n"
        )
    )

    with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=20) as server:
        server.starttls()
        server.login(settings.smtp_username, settings.smtp_password)
        server.send_message(msg)
