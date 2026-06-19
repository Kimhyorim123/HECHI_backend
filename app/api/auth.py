from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status, Query, Response, Request, Body
from fastapi.responses import JSONResponse
from pydantic import EmailStr
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import User
from ..schemas.user import UserCreate, UserRead, UserUpdate
from ..schemas.auth import (
    LoginRequest,
    TokenPair,
    RefreshRequest,
    EmailCheckResponse,
    LoginIdCheckResponse,
    VerifyEmailRequest,
    ResendVerificationRequest,
    VerificationStatusResponse,
)
from ..core.security import (
    hash_password,
    verify_password,
    create_access_token,
    create_refresh_token,
    decode_token,
)
from ..core.config import get_settings
from ..core.auth import get_current_user
from ..services.email_verification import (
    can_resend,
    generate_verification_code,
    hash_verification_code,
    send_verification_email,
    smtp_enabled,
    verification_expiry,
    verify_verification_code,
)

router = APIRouter(prefix="/auth", tags=["auth"])


def _serialize_user(user: User) -> UserRead:
    return UserRead(
        id=user.id,
        email=user.email,
        login_id=user.login_id,
        name=user.name,
        nickname=user.nickname,
        description=user.description,
        profileImageUrl=user.profile_image_url,
        created_at=user.created_at,
        taste_analyzed=user.taste_analyzed,
        email_verified=user.email_verified,
    )

@router.post("/register", response_model=UserRead, status_code=status.HTTP_201_CREATED)
def register(data: UserCreate, db: Session = Depends(get_db)):
    existing_email = db.query(User).filter(User.email == data.email).first()
    if existing_email:
        raise HTTPException(status_code=400, detail="Email already registered")
    existing_login_id = db.query(User).filter(User.login_id == data.login_id).first()
    if existing_login_id:
        raise HTTPException(status_code=400, detail="Login ID already registered")
    should_verify_email = smtp_enabled()
    verification_code = generate_verification_code() if should_verify_email else None
    user = User(
        email=data.email,
        login_id=data.login_id,
        password_hash=hash_password(data.password),
        email_verified=not should_verify_email,
        email_verification_code_hash=hash_verification_code(verification_code) if verification_code else None,
        email_verification_expires_at=verification_expiry() if verification_code else None,
        email_verification_sent_at=datetime.now(timezone.utc) if verification_code else None,
        email_verified_at=None if should_verify_email else datetime.now(timezone.utc),
        name=data.name,
        nickname=data.nickname,
    )
    db.add(user)
    db.flush()
    if verification_code:
        try:
            send_verification_email(user.email, verification_code)
        except Exception:
            db.rollback()
            raise HTTPException(status_code=502, detail="Failed to send verification email")
    db.commit()
    db.refresh(user)
    return _serialize_user(user)

@router.post("/login", response_model=TokenPair)
def login(data: LoginRequest, response: Response, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.login_id == data.login_id).first()
    if not user or not verify_password(data.password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
    if smtp_enabled() and not user.email_verified:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Email not verified")
    access = create_access_token(user.id)
    refresh = create_refresh_token(user.id)
    # remember_me가 true인 경우, refresh 토큰을 HttpOnly 쿠키로 설정하여 자동로그인 지원
    # 응답을 직접 구성하여 쿠키를 확실히 설정
    resp_body = TokenPair(access_token=access, refresh_token=refresh).model_dump()
    resp = JSONResponse(content=resp_body)
    if data.remember_me:
        from ..core.config import get_settings
        settings = get_settings()
        max_age = settings.refresh_token_exp_days * 24 * 60 * 60
        secure_flag = settings.environment != "local"
        resp.set_cookie(
            key="refresh_token",
            value=refresh,
            httponly=True,
            secure=secure_flag,
            samesite="lax",
            max_age=max_age,
            path="/",
        )
    return resp

@router.post("/refresh", response_model=TokenPair)
def refresh_token(request: Request, data: RefreshRequest | None = Body(default=None)):
    # 본문에 refresh_token이 없으면 쿠키에서 읽어 자동로그인 지원
    token = (data.refresh_token if data else None) or request.cookies.get("refresh_token")
    if not token:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Missing refresh token")
    payload = decode_token(token, expected_type="refresh")
    user_id = int(payload["sub"])  # type: ignore
    return TokenPair(access_token=create_access_token(user_id), refresh_token=create_refresh_token(user_id))

@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT, summary="로그아웃 (refresh 쿠키 삭제)")
def logout(_: Response):
    resp = JSONResponse(content=None, status_code=status.HTTP_204_NO_CONTENT)
    # 표준 삭제
    resp.delete_cookie("refresh_token", path="/")
    # 일부 클라이언트/프록시 환경에서 delete_cookie가 누락될 수 있어 수동 헤더도 추가
    from ..core.config import get_settings
    settings = get_settings()
    secure_flag = settings.environment != "local"
    cookie = "refresh_token=; Max-Age=0; Path=/; SameSite=lax; HttpOnly"
    if secure_flag:
        cookie += "; Secure"
    resp.headers.append("Set-Cookie", cookie)
    return resp

@router.get("/me", response_model=UserRead)
def me(current_user: User = Depends(get_current_user)):
    return _serialize_user(current_user)


@router.patch("/me", response_model=UserRead, summary="내 프로필 수정")
def update_me(
    payload: UserUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    changed = False
    if payload.name is not None and payload.name.strip() != "" and payload.name != current_user.name:
        current_user.name = payload.name.strip()
        changed = True
    if payload.nickname is not None and payload.nickname.strip() != "" and payload.nickname != current_user.nickname:
        current_user.nickname = payload.nickname.strip()
        changed = True
    if payload.description is not None and payload.description != current_user.description:
        current_user.description = payload.description
        changed = True
    if changed:
        db.add(current_user)
        db.commit()
        db.refresh(current_user)
    return _serialize_user(current_user)


@router.get("/email-check", response_model=EmailCheckResponse, summary="이메일 존재/가용성 확인")
def email_check(
    email: EmailStr = Query(..., description="확인할 이메일 주소"),
    db: Session = Depends(get_db),
):
    # 존재 여부 확인
    exists = db.query(User.id).filter(User.email == email).first() is not None
    return EmailCheckResponse(exists=exists, available=not exists)


@router.get("/login-id-check", response_model=LoginIdCheckResponse, summary="로그인 ID 존재/가용성 확인")
def login_id_check(
    login_id: str = Query(..., min_length=3, description="확인할 로그인 ID"),
    db: Session = Depends(get_db),
):
    exists = db.query(User.id).filter(User.login_id == login_id).first() is not None
    return LoginIdCheckResponse(exists=exists, available=not exists)


@router.post("/verify-email", response_model=VerificationStatusResponse, summary="이메일 인증 코드 확인")
def verify_email(
    data: VerifyEmailRequest,
    db: Session = Depends(get_db),
):
    user = db.query(User).filter(User.email == data.email).first()
    if not user:
        raise HTTPException(status_code=404, detail="Email not found")
    if user.email_verified:
        return VerificationStatusResponse(ok=True, email_verified=True, detail="Email already verified")
    expires_at = user.email_verification_expires_at
    now = datetime.now(timezone.utc)
    if not expires_at:
        raise HTTPException(status_code=400, detail="Verification code not requested")
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    if now > expires_at:
        raise HTTPException(status_code=400, detail="Verification code expired")
    if not verify_verification_code(data.code, user.email_verification_code_hash):
        raise HTTPException(status_code=400, detail="Invalid verification code")
    user.email_verified = True
    user.email_verified_at = now
    user.email_verification_code_hash = None
    user.email_verification_expires_at = None
    user.email_verification_sent_at = None
    db.add(user)
    db.commit()
    return VerificationStatusResponse(ok=True, email_verified=True, detail="Email verified")


@router.post("/verify-email/resend", response_model=VerificationStatusResponse, summary="이메일 인증 코드 재발송")
def resend_verification_email(
    data: ResendVerificationRequest,
    db: Session = Depends(get_db),
):
    user = db.query(User).filter(User.email == data.email).first()
    if not user:
        raise HTTPException(status_code=404, detail="Email not found")
    if user.email_verified:
        return VerificationStatusResponse(ok=True, email_verified=True, detail="Email already verified")
    if not smtp_enabled():
        user.email_verified = True
        user.email_verified_at = datetime.now(timezone.utc)
        user.email_verification_code_hash = None
        user.email_verification_expires_at = None
        user.email_verification_sent_at = None
        db.add(user)
        db.commit()
        return VerificationStatusResponse(ok=True, email_verified=True, detail="SMTP not configured; email marked verified")
    if not can_resend(user.email_verification_sent_at):
        settings = get_settings()
        raise HTTPException(
            status_code=429,
            detail=f"Please wait {settings.email_verification_resend_seconds} seconds before resending",
        )
    verification_code = generate_verification_code()
    user.email_verification_code_hash = hash_verification_code(verification_code)
    user.email_verification_expires_at = verification_expiry()
    user.email_verification_sent_at = datetime.now(timezone.utc)
    db.add(user)
    try:
        send_verification_email(user.email, verification_code)
    except Exception:
        db.rollback()
        raise HTTPException(status_code=502, detail="Failed to send verification email")
    db.commit()
    return VerificationStatusResponse(ok=True, email_verified=False, detail="Verification email sent")
