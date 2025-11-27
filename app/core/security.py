from datetime import datetime, timedelta, timezone
import uuid
from typing import Any, Dict
from jose import jwt, JWTError
from passlib.context import CryptContext
from fastapi import HTTPException, status

from .config import get_settings

# Use pbkdf2_sha256 to avoid native bcrypt backend issues and keep portability
pwd_context = CryptContext(schemes=["pbkdf2_sha256"], deprecated="auto")


def hash_password(raw: str) -> str:
    return pwd_context.hash(raw)


def verify_password(raw: str, hashed: str) -> bool:
    return pwd_context.verify(raw, hashed)


def _create_token(subject: str, expires_delta: timedelta, token_type: str) -> str:
    settings = get_settings()
    # Use timezone-aware UTC to avoid local-time offset issues on .timestamp()
    now = datetime.now(timezone.utc)
    to_encode: Dict[str, Any] = {
        "sub": subject,
        "iat": int(now.timestamp()),
        "exp": int((now + expires_delta).timestamp()),
        "type": token_type,
        # ensure uniqueness even within the same second
        "jti": uuid.uuid4().hex,
    }
    return jwt.encode(to_encode, settings.secret_key, algorithm=settings.jwt_algorithm)


def create_access_token(user_id: int) -> str:
    settings = get_settings()
    return _create_token(str(user_id), timedelta(minutes=settings.access_token_exp_minutes), "access")


def create_refresh_token(user_id: int) -> str:
    settings = get_settings()
    return _create_token(str(user_id), timedelta(days=settings.refresh_token_exp_days), "refresh")


def decode_token(token: str, expected_type: str) -> Dict[str, Any]:
    settings = get_settings()
    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=[settings.jwt_algorithm])
        if payload.get("type") != expected_type:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token type")
        return payload
    except JWTError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token invalid or expired")
